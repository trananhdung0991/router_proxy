import os
import subprocess
import time
import random
import string
import re
import logging
import threading
from typing import Dict, List, Optional

# Known DoH (DNS-over-HTTPS) resolver IPs — block these per-device to prevent
# Chrome/Firefox bypassing the per-device dnsmasq via encrypted HTTPS DNS.
DOH_BLOCK_IPS = [
    '8.8.8.8', '8.8.4.4',           # Google
    '1.1.1.1', '1.0.0.1',           # Cloudflare
    '9.9.9.9', '149.112.112.112',    # Quad9
    '208.67.222.222', '208.67.220.220',  # OpenDNS
]

# DoH endpoint hostnames — poison these in per-device dnsmasq (return 0.0.0.0)
# so browsers cannot resolve the DoH server and fall back to plain UDP 53.
# Chrome uses chrome.cloudflare-dns.com (resolves to 162.158.x, 172.x.x.x, etc.)
# which are NOT in DOH_BLOCK_IPS, so hostname poisoning is the effective method.
DOH_HOSTNAMES = [
    # Google
    'dns.google', 'dns.google.com',
    # Cloudflare (Chrome, Firefox, Mozilla)
    'cloudflare-dns.com', 'chrome.cloudflare-dns.com', 'mozilla.cloudflare-dns.com',
    '1dot1dot1dot1.cloudflare-dns.com',
    # Quad9
    'dns.quad9.net', 'dns10.quad9.net', 'dns11.quad9.net',
    # OpenDNS
    'doh.opendns.com', 'doh.familyshield.opendns.com',
    # Others
    'dns.adguard.com', 'dns-family.adguard.com',
    'doh.cleanbrowsing.org',
    'doh.dns.apple.com',
    'dns.nextdns.io',
    'doh.xfinity.com',
]

# STUN hostnames browsers use for WebRTC IP discovery
STUN_HOSTNAMES = [
    'stun.l.google.com', 'stun1.l.google.com', 'stun2.l.google.com',
    'stun3.l.google.com', 'stun4.l.google.com',
    'global.stun.twilio.com', 'stun.cloudflare.com',
    'stun.relay.metered.ca', 'stunserver.stunprotocol.org',
]
_ROUTER_LAN_IP = '192.168.1.1'

# Set up logging
logger = logging.getLogger(__name__)

class Passwall2Manager:
    """
    Manage Passwall2 proxy configurations via UCI commands
    """
    
    def __init__(self):
        self.config_name = 'passwall2'
    
    def run_uci_command(self, cmd: List[str]) -> str:
        """Execute UCI command and return output"""
        try:
            result = subprocess.run(['uci'] + cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if 'delete' in cmd and ('not found' in e.stderr.lower()):
                return ""
            logger.error(f"UCI command failed: {e}")
            return ""
    
    def section_exists(self, section_name: str) -> bool:
        """Check if a UCI section exists"""
        try:
            result = subprocess.run(['uci', 'get', f'{self.config_name}.{section_name}'], 
                                  capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False

    def add_proxy_node(self, name: str, server: str, port: int,
                       protocol: str = 'http', username: str = '',
                       password: str = '') -> str:
        """Add proxy node using direct section creation."""
        try:
            # Check specifically for 'Local HTTP Proxy' main node
            if name == "Local HTTP Proxy":
                existing_nodes = self.get_nodes()
                for node in existing_nodes:
                    if node.get('remarks') == 'Local HTTP Proxy':
                        logger.info(f"Main HTTP proxy node 'Local HTTP Proxy' already exists: {node['section']}")
                        return node['section']
                logger.info(f"Main HTTP proxy node 'Local HTTP Proxy' not found, creating new one...")
            else:
                # Check if a node with the same configuration already exists (for other nodes)
                existing_nodes = self.get_nodes()
                for node in existing_nodes:
                    if (node.get('address') == server and 
                        node.get('port') == str(port) and 
                        node.get('protocol') == protocol and
                        node.get('remarks') == name):
                        logger.info(f"{protocol.upper()} node '{name}' already exists: {node['section']}")
                        return node['section']
            
            # Generate a unique section name that doesn't start with 'node_'
            section_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            
            logger.info(f"Creating {protocol} node with section: {section_name}")
            
            # Create the section directly
            self.run_uci_command(['set', f'{self.config_name}.{section_name}=nodes'])
            
            # Set node type and protocol - ALL proxies use Xray type
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.type=Xray'])
            
            if protocol.lower() in ['socks4', 'socks5']:
                # SOCKS proxies use 'socks' protocol with Xray type
                self.run_uci_command(['set', f'{self.config_name}.{section_name}.protocol=socks'])
            elif protocol.lower() in ['http', 'https']:
                self.run_uci_command(['set', f'{self.config_name}.{section_name}.protocol=http'])
            else:
                # Default to HTTP
                self.run_uci_command(['set', f'{self.config_name}.{section_name}.protocol=http'])
    
            # Set common properties
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.remarks={name}'])
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.address={server}'])
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.port={port}'])
            
            # Set authentication if provided
            if username:
                self.run_uci_command(['set', f'{self.config_name}.{section_name}.username={username}'])
            if password:
                self.run_uci_command(['set', f'{self.config_name}.{section_name}.password={password}'])
            
            # Set standard properties for all Xray nodes
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.tls=0'])
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.transport=raw'])
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.tcp_guise=none'])
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.tcpMptcp=0'])
            self.run_uci_command(['set', f'{self.config_name}.{section_name}.tcpNoDelay=0'])
        
            # Commit changes
            self.run_uci_command(['commit', self.config_name])
            
            # NOTE: Do NOT set as main TCP/UDP node - let the caller decide
            # The node is created for client-specific ACL rules, not global routing
            
            # Clear LuCI cache to refresh web interface
            subprocess.run(['rm', '-rf', '/tmp/luci-*'], check=False)
            
            # Verify the node was created
            verify = self.run_uci_command(['show', f'{self.config_name}.{section_name}'])
            
            if verify:
                logger.info(f"Node created successfully: {section_name}")
                return section_name
            else:
                logger.error(f"Node creation failed: {section_name}")
                return ""
            
        except Exception as e:
            logger.error(f"Error creating proxy node: {e}")
            import traceback
            traceback.print_exc()
            return ""


    def _uci_get_quiet(self, key: str) -> str:
        """uci get that returns '' instead of raising on missing entries."""
        res = subprocess.run(['uci', 'get', key], capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else ""

    def _restart_passwall2(self) -> bool:
        """Safely restart passwall2: kill all related processes (including nft/awk children),
        flush the nft table, clean temp dirs, then start fresh."""
        try:
            # Stop gracefully first (best-effort, may fail if already dead)
            subprocess.run(['/etc/init.d/passwall2', 'stop'], capture_output=True, text=True, timeout=10)
            time.sleep(2)

            # Kill all child processes that stop doesn't clean up
            # Use busybox-compatible sh+ps+awk (OpenWrt has no pkill)
            kill_patterns = ['app\\.sh', 'passwall', 'awk.*passwall', 'dnsmasq.*passwall', 'xray']
            for pattern in kill_patterns:
                subprocess.run(
                    ['/bin/sh', '-c',
                     f"kill -9 $(ps | grep -E '{pattern}' | grep -v grep | awk '{{print $1}}') 2>/dev/null; true"],
                    capture_output=True)
            subprocess.run(['/usr/bin/killall', '-9', 'nft'], capture_output=True)
            time.sleep(2)

            # Remove lock files and runtime dirs
            subprocess.run(['rm', '-f', '/var/lock/passwall2.lock', '/var/lock/passwall2_ready.lock'],
                           capture_output=True)
            subprocess.run(['rm', '-rf', '/tmp/etc/passwall2', '/var/etc/passwall2'], capture_output=True)

            # Delete stale nft table so the next start creates it cleanly
            subprocess.run(['nft', 'delete', 'table', 'inet', 'passwall2'], capture_output=True)

            # Start passwall2 in background (non-blocking, detached session)
            subprocess.Popen(
                ['/bin/sh', '-c', '/etc/init.d/passwall2 start >/tmp/pw2_start.log 2>&1'],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            # Spawn background thread to re-inject STUN DNS once passwall2 is ready
            threading.Thread(
                target=self._post_restart_inject_stun,
                daemon=True, name='stun-inject'
            ).start()
            logger.info("passwall2 safe restart initiated")
            return True
        except Exception as e:
            logger.error(f"Error during passwall2 safe restart: {e}")
            return False


    def set_global_direct(self) -> bool:
        """Set global passwall2 routing to direct — unassigned devices bypass proxy and
        go straight to the internet. ACL rules still apply per-device."""
        try:
            subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].tcp_node=direct'], check=False)
            subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].udp_node=direct'], check=False)
            # Remove the legacy 'node' key if present — it conflicts with direct mode
            subprocess.run(['uci', 'delete', f'{self.config_name}.@global[0].node'],
                           capture_output=True)
            subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].enabled=1'], check=False)
            subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].acl_enable=1'], check=False)
            subprocess.run(['uci', 'commit', self.config_name], check=False)
            logger.info("Global passwall2 routing set to direct (unassigned devices bypass proxy)")
            return True
        except Exception as e:
            logger.error(f"Error setting global direct: {e}")
            return False

    def _remove_local_proxy_node(self) -> None:
        """Remove the legacy 'Local HTTP Proxy' passwall2 node if it exists."""
        for node in self.get_nodes():
            if (node.get('address') == '127.0.0.1' and
                    node.get('port') == '4001' and
                    node.get('protocol') == 'http'):
                logger.info(f"Removing legacy Local HTTP Proxy node: {node['section']}")
                self.remove_node(node['section'])

    def set_client_proxy_rule(self, client_ip: str, node_section: str,
                               remote_fakedns: bool = False,
                               proxy_server_ip: str = '') -> bool:
        """Set ACL rule for client to use specific proxy node.
        Global nodes (tcp_node/udp_node) are NOT changed here — they stay
        at 'direct' so unassigned devices bypass the proxy."""
        try:
            logger.info(f"Creating ACL rule for client {client_ip} using node {node_section}")

            # Remove any existing ACL rules for this client (without restart)
            logger.info(f"Removing existing ACL rules for {client_ip}")
            self.remove_client_proxy_rule(client_ip, restart_service=False)

            # Small delay to ensure cleanup is complete
            time.sleep(1)

            # Generate a unique remarks ID
            remarks_id = 'cfg' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

            # Create anonymous ACL rule section
            add_result = self.run_uci_command(['add', self.config_name, 'acl_rule'])
            if not add_result:
                logger.error("Failed to create ACL rule section")
                return False

            section_name = add_result.strip()
            logger.info(f"Created ACL section: {section_name}")

            commands = [
                ['set', f'{self.config_name}.{section_name}.enabled=1'],
                ['set', f'{self.config_name}.{section_name}.remarks={remarks_id}'],
                ['set', f'{self.config_name}.{section_name}.sources={client_ip}'],
                ['set', f'{self.config_name}.{section_name}.node={node_section}'],
                ['set', f'{self.config_name}.{section_name}.direct_dns_query_strategy=UseIP'],
                ['set', f'{self.config_name}.{section_name}.remote_dns_protocol=tcp'],
                ['set', f'{self.config_name}.{section_name}.remote_dns=1.1.1.1'],
                ['set', f'{self.config_name}.{section_name}.remote_dns_detour=remote'],
                ['set', f'{self.config_name}.{section_name}.remote_fakedns={"1" if remote_fakedns else "0"}'],
                ['set', f'{self.config_name}.{section_name}.remote_dns_query_strategy=UseIPv4'],
            ]
            for cmd in commands:
                self.run_uci_command(cmd)

            # Commit ACL rule
            self.run_uci_command(['commit', self.config_name])

            logger.info(f"Remote FakeDNS: {'enabled' if remote_fakedns else 'disabled'}")

            # Register device with STUN server for WebRTC IP spoofing
            if proxy_server_ip:
                from router.stun_server import get_stun_server
                get_stun_server().register(client_ip, proxy_server_ip)
                logger.info(f"STUN: registered {client_ip} → {proxy_server_ip}")

            logger.info(f"Restarting Passwall2 to apply rule for {client_ip}")
            self._restart_passwall2()  # also spawns _post_restart_inject_stun thread

            logger.info(f"Successfully created ACL rule for {client_ip}")
            return True

        except Exception as e:
            logger.error(f"Error setting client rule: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_nodes(self) -> List[Dict[str, str]]:
        """Get all proxy nodes"""
        try:
            cfg = self.run_uci_command(['show', self.config_name])
            nodes = []
            current_node = {}
            current_section = None

            for line in cfg.splitlines():
                if '=nodes' in line:
                    if current_node:
                        nodes.append(current_node)
                    current_section = line.split('.')[1].split('=')[0]
                    current_node = {'section': current_section}
                elif current_section and line.startswith(f'{self.config_name}.{current_section}.'):
                    key = line.split('.', 2)[-1].split('=', 1)[0]
                    val = line.split('=', 1)[1].strip().strip("'\"")
                    current_node[key] = val

            if current_node:
                nodes.append(current_node)

            # Process nodes to format protocol display correctly
            for node in nodes:
                protocol = node.get('protocol', 'unknown')
                socks_version = node.get('socks_version', '')
                node_type = node.get('type', 'Unknown')
                
                # Format protocol display for SOCKS
                if protocol == 'socks' and socks_version:
                    node['display_protocol'] = f"socks{socks_version}"
                else:
                    node['display_protocol'] = protocol
                    
                # Format display name
                remarks = node.get('remarks', node.get('section', ''))
                display_protocol = node['display_protocol']
                node['display_name'] = f"{node_type} {display_protocol.title()} : {remarks}"

            return nodes
        except Exception as e:
            logger.error(f"Error getting nodes: {e}")
            return []

    def get_acl_rules(self) -> List[Dict[str, str]]:
        """Return all ACL rules with their node references resolved"""
        try:
            out = self.run_uci_command(['show', self.config_name])
            rules = {}
            nodes = {n['section']: n for n in self.get_nodes()}
            
            for line in out.splitlines():
                if not line or '=' not in line:
                    continue
                left, right = line.split('=', 1)
                parts = left.split('.')
                if len(parts) < 2:
                    continue
                section = parts[1]
                
                # ACL rule section
                if right.strip() == 'acl_rule':
                    rules.setdefault(section, {})
                    rules[section]['section'] = section
                elif len(parts) >= 3 and section in rules:
                    key = parts[2]
                    value = right.strip().strip("'\"")
                    rules[section][key] = value
                    
                    # Resolve node reference
                    if key == 'node' and value in nodes:
                        node_info = nodes[value]
                        rules[section]['node_name'] = node_info.get('remarks', value)
                        rules[section]['node_type'] = node_info.get('type', 'unknown')
                        rules[section]['node_protocol'] = node_info.get('protocol', 'unknown')
            
            return list(rules.values())
        except Exception as e:
            logger.error(f"Error parsing ACL rules: {e}")
            return []

    def remove_node(self, section_name: str) -> bool:
        """Delete a node section safely."""
        try:
            if self.section_exists(section_name):
                self.run_uci_command(['delete', f'{self.config_name}.{section_name}'])
                self.run_uci_command(['commit', self.config_name])
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing node {section_name}: {e}")
            return False

    def remove_client_proxy_rule(self, client_ip: str, restart_service: bool = True) -> bool:
        """Remove ACL rule(s) for client and delete unused nodes it referenced."""
        try:
            logger.info(f"=== Removing proxy rules for client: {client_ip} ===")
            cfg = self.run_uci_command(['show', self.config_name])

            # Collect ACL sections and fields  
            acl_map: Dict[str, Dict[str, str]] = {}
            current = None
            for line in cfg.splitlines():
                if '=acl_rule' in line:
                    current = line.split('=')[0].split('.', 1)[1]
                    acl_map.setdefault(current, {})
                elif current and line.startswith(f'{self.config_name}.{current}.'):
                    key = line.split('.', 2)[-1].split('=', 1)[0]
                    val = line.split('=', 1)[1].strip().strip('\'"')
                    acl_map[current][key] = val

            logger.info(f"Found ACL sections: {list(acl_map.keys())}")

            # Find ACLs for this client and collect referenced nodes
            to_delete = []
            candidate_nodes = set()
            for sec, data in acl_map.items():
                logger.info(f"Checking ACL {sec}: sources={data.get('sources')}, node={data.get('node')}")
                if data.get('sources') == client_ip:
                    to_delete.append(sec)
                    if data.get('node'):
                        candidate_nodes.add(data['node'])
                        logger.info(f"Found ACL rule {sec} using node {data['node']} - WILL DELETE")

            logger.info(f"ACL sections to delete: {to_delete}")
            logger.info(f"Candidate nodes for removal: {candidate_nodes}")

            # Delete ACLs first
            for sec in to_delete:
                logger.info(f"Removing ACL rule section: {sec}")
                self.run_uci_command(['delete', f'{self.config_name}.{sec}'])

            if to_delete:
                self.run_uci_command(['commit', self.config_name])

            # If global nodes pointed to the deleted candidate, restore them to direct
            current_tcp = self._uci_get_quiet(f'{self.config_name}.@global[0].tcp_node')
            current_udp = self._uci_get_quiet(f'{self.config_name}.@global[0].udp_node')
            current_main = self._uci_get_quiet(f'{self.config_name}.@global[0].node')
            global_pointed_at_candidate = (
                current_tcp in candidate_nodes or
                current_udp in candidate_nodes or
                current_main in candidate_nodes
            )

            # Now check which nodes are still in use BEFORE deleting
            still_used = self._nodes_in_use()

            # Remove nodes that are only referenced by the deleted ACL rules
            nodes_to_remove = candidate_nodes - still_used
            logger.info(f"Nodes to remove: {nodes_to_remove}")

            for node in nodes_to_remove:
                if node:
                    logger.info(f"Removing unused node: {node}")
                    result = self.remove_node(node)
                    logger.info(f"Node {node} removal result: {result}")

            # Restore global nodes to direct if they pointed at a removed node
            if global_pointed_at_candidate:
                logger.info("Restoring global nodes to direct (bypass)")
                subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].tcp_node=direct'], check=False)
                subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].udp_node=direct'], check=False)
                subprocess.run(['uci', 'delete', f'{self.config_name}.@global[0].node'], capture_output=True)
                subprocess.run(['uci', 'commit', self.config_name], check=False)

            # Optional restart only if requested
            if (to_delete or nodes_to_remove) and restart_service:
                logger.info("Restarting Passwall2 service")
                self._restart_passwall2()

            # Unregister from STUN server and remove STUN-related rules
            try:
                from router.stun_server import get_stun_server
                get_stun_server().unregister(client_ip)
            except Exception:
                pass
            self._remove_stun_dns(client_ip)
            self._remove_stun_nft_rules(client_ip)
            self._remove_doh_block_rules(client_ip)

            logger.info(f"=== Successfully processed removal for {client_ip} ===")
            return True
        except Exception as e:
            logger.error(f"Error removing client rule: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _nodes_in_use(self) -> set:
        """Nodes referenced by any ACL or as global tcp/udp/main node."""
        used = set()
        try:
            cfg = self.run_uci_command(['show', self.config_name])
            
            # Parse all ACL rules and global settings
            acl_sections = {}
            current_acl = None
            
            for line in cfg.splitlines():
                if not line or '=' not in line:
                    continue
                    
                left, right = line.split('=', 1)
                right = right.strip().strip("'\"")
                
                # Check for ACL rule sections
                if '=acl_rule' in line:
                    section_name = left.split('.')[1]
                    current_acl = section_name
                    acl_sections[current_acl] = {}
                    logger.debug(f"Found ACL section: {current_acl}")
                
                # Check for ACL rule properties
                elif current_acl and line.startswith(f'{self.config_name}.{current_acl}.'):
                    field = line.split('.', 2)[2].split('=')[0]
                    acl_sections[current_acl][field] = right
                    if field == 'node' and right:
                        logger.debug(f"ACL {current_acl} references node: {right}")
                
                # Check for global TCP/UDP/main nodes
                elif ('.@global[0].tcp_node=' in line or 
                      '.@global[0].udp_node=' in line or 
                      '.@global[0].node=' in line):
                    if right:
                        used.add(right)
                        logger.debug(f"Found global node in use: {right}")
            
            # Check all ACL rules for node references
            for acl_name, acl_data in acl_sections.items():
                node_ref = acl_data.get('node')
                sources = acl_data.get('sources')
                enabled = acl_data.get('enabled')
                
                logger.debug(f"ACL {acl_name}: node={node_ref}, sources={sources}, enabled={enabled}")
                
                # Only consider enabled ACL rules
                if node_ref and enabled == '1':
                    used.add(node_ref)
                    logger.debug(f"Found ACL node in use: {node_ref} (from ACL {acl_name})")
                    
            logger.debug(f"Total nodes in use: {used}")
        except Exception as e:
            logger.error(f"Error scanning used nodes: {e}")
            import traceback
            traceback.print_exc()
        return used

    def get_global_config(self) -> Dict[str, str]:
        """Get current global configuration"""
        try:
            config = {}
            
            # Get main settings
            config['enabled'] = self._uci_get_quiet(f'{self.config_name}.@global[0].enabled')
            config['client_proxy'] = self._uci_get_quiet(f'{self.config_name}.@global[0].client_proxy')
            config['acl_enable'] = self._uci_get_quiet(f'{self.config_name}.@global[0].acl_enable')
            config['tcp_node'] = self._uci_get_quiet(f'{self.config_name}.@global[0].tcp_node')
            config['udp_node'] = self._uci_get_quiet(f'{self.config_name}.@global[0].udp_node')
            config['node'] = self._uci_get_quiet(f'{self.config_name}.@global[0].node')  # Add this line
            
            # Check if nodes exist
            tcp_node = config['tcp_node']
            udp_node = config['udp_node']
            main_node = config['node']
            config['tcp_node_exists'] = bool(tcp_node and self.section_exists(tcp_node))
            config['udp_node_exists'] = bool(udp_node and self.section_exists(udp_node))
            config['node_exists'] = bool(main_node and self.section_exists(main_node))
            
            return config
        except Exception as e:
            logger.error(f"Error getting global config: {e}")
            return {}

    # ------------------------------------------------------------------ #
    #  WebRTC / STUN spoofing helpers                                     #
    # ------------------------------------------------------------------ #

    def _get_acl_dir_for_device(self, device_ip: str) -> Optional[str]:
        """Find the passwall2 ACL runtime directory for *device_ip* by scanning
        source_list files (which contain 'ip:<device_ip>'). Returns the dir path
        e.g. '/var/etc/passwall2/acl/cfg1030ec', or None if not found."""
        for base in ['/var/etc/passwall2/acl', '/tmp/etc/passwall2/acl']:
            try:
                for entry in os.listdir(base):
                    src = os.path.join(base, entry, 'source_list')
                    try:
                        with open(src, 'r') as f:
                            if f'ip:{device_ip}' in f.read():
                                return os.path.join(base, entry)
                    except OSError:
                        continue
            except OSError:
                continue
        return None

    def _inject_stun_dns(self, device_ip: str) -> bool:
        """Inject STUN hostname overrides and DoH hostname poison into the per-device
        dnsmasq conf-dir and system dnsmasq (/tmp/dnsmasq.d/) as a fallback.
        - STUN hostnames → router LAN IP (WebRTC spoofing)
        - DoH hostnames  → 0.0.0.0 (forces browser DoH fallback to plain UDP 53)"""
        try:
            # Single conf block: STUN spoofing + DoH endpoint poisoning
            stun_overrides = (
                '# STUN address overrides - WebRTC IP spoofing\n' +
                '\n'.join(f'address=/{h}/{_ROUTER_LAN_IP}' for h in STUN_HOSTNAMES) + '\n' +
                '# DoH endpoint poisoning - return 0.0.0.0 so browsers fall back to plain UDP 53\n' +
                '\n'.join(f'address=/{h}/0.0.0.0' for h in DOH_HOSTNAMES) + '\n'
            )
            injected_perdev = False

            # ── per-device dnsmasq (passwall2 ACL instance) ─────────────── #
            acl_dir = self._get_acl_dir_for_device(device_ip)
            if acl_dir:
                # Read dnsmasq.conf to find the conf-dir directive
                dnsmasq_conf = os.path.join(acl_dir, 'dnsmasq.conf')
                conf_dir = None
                try:
                    with open(dnsmasq_conf, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('conf-dir='):
                                conf_dir = line.split('=', 1)[1]
                                break
                except OSError:
                    pass

                if conf_dir:
                    os.makedirs(conf_dir, exist_ok=True)
                    stun_conf = os.path.join(conf_dir, 'stun_override.conf')
                    with open(stun_conf, 'w') as f:
                        f.write(stun_overrides)
                    logger.info(f"STUN+DoH DNS injected into {stun_conf}")
                    injected_perdev = True

                    # Restart the per-device dnsmasq so it picks up the new conf-dir file.
                    # (SIGHUP only reloads hosts files, not conf-dir entries.)
                    section_id = os.path.basename(acl_dir)
                    bin_path = f'/tmp/etc/passwall2/bin/dnsmasq_{section_id}'
                    tmp_conf  = f'/tmp/etc/passwall2/acl/{section_id}/dnsmasq.conf'
                    tmp_pid   = f'/tmp/etc/passwall2/acl/{section_id}/dnsmasq.pid'
                    pid_file  = os.path.join(acl_dir, 'dnsmasq.pid')
                    try:
                        with open(pid_file, 'r') as f:
                            old_pid = f.read().strip()
                        if old_pid:
                            subprocess.run(['kill', old_pid], capture_output=True)
                            time.sleep(0.5)
                        # Re-launch with same cmdline
                        subprocess.Popen(
                            [bin_path, '-C', tmp_conf, '-x', tmp_pid],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                        logger.info(f"Restarted per-device dnsmasq ({section_id}) for {device_ip}")
                    except OSError as exc:
                        logger.warning(f"Could not restart per-device dnsmasq: {exc}")
                else:
                    logger.warning(f"No conf-dir found in {dnsmasq_conf}")
            else:
                logger.warning(f"No ACL dir found for {device_ip} — skipping per-device DNS injection")

            # ── system dnsmasq fallback ──────────────────────────────────── #
            subprocess.run(['mkdir', '-p', '/tmp/dnsmasq.d'], capture_output=True)
            with open('/tmp/dnsmasq.d/stun_override.conf', 'w') as f:
                f.write(stun_overrides)
            subprocess.run(
                ['/bin/sh', '-c',
                 'kill -HUP $(cat /var/run/dnsmasq/*.pid 2>/dev/null | head -1) 2>/dev/null; true'],
                capture_output=True
            )
            logger.info(f"STUN DNS injection complete for {device_ip} (per-device={injected_perdev})")
            return True
        except Exception as e:
            logger.error(f"Error injecting STUN DNS for {device_ip}: {e}")
            return False

    def _remove_stun_dns(self, device_ip: str) -> None:
        """Remove system-wide STUN DNS overrides if no devices remain registered."""
        try:
            from router.stun_server import get_stun_server
            remaining = get_stun_server().get_all()
            if not remaining:
                subprocess.run(['rm', '-f', '/tmp/dnsmasq.d/stun_override.conf'], capture_output=True)
                subprocess.run(
                    ['/bin/sh', '-c',
                     'kill -HUP $(cat /var/run/dnsmasq/*.pid 2>/dev/null | head -1) 2>/dev/null; true'],
                    capture_output=True
                )
                logger.info("STUN DNS overrides removed (no proxied devices remaining)")
        except Exception as e:
            logger.debug(f"_remove_stun_dns: {e}")

    def _add_stun_nft_rules(self, device_ip: str) -> None:
        """Two-step STUN interception for *device_ip*:
        1. PSW2_MANGLE return  — prevents passwall2 tproxy from capturing STUN UDP
        2. passwall2 dstnat redirect — sends ALL STUN UDP to the local fake STUN server
           (works regardless of whether the browser uses DNS spoof or DoH real IP)
        """
        try:
            self._remove_stun_nft_rules(device_ip)   # idempotent
            safe_ip = device_ip.replace('.', '_')

            # Step 1: bypass tproxy in PSW2_MANGLE (mangle hook priority -151)
            #   Insert at the beginning so it fires before the catch-all tproxy rule.
            #   Include port 19302 (Google STUN default used by Chrome WebRTC).
            bypass_cmd = (
                f"nft insert rule inet passwall2 PSW2_MANGLE "
                f"ip saddr {device_ip} udp dport '{{ 3478, 3479, 5349, 19302 }}' "
                f"return comment '\"stun_bypass_{safe_ip}\"'"
            )
            r = subprocess.run(['/bin/sh', '-c', bypass_cmd], capture_output=True, text=True)
            if r.returncode == 0:
                logger.info(f"nftables STUN tproxy bypass added for {device_ip}")
            else:
                logger.warning(f"nft STUN bypass failed for {device_ip}: {r.stderr.strip()}")

            # Step 2: DNAT all STUN UDP from device → local fake STUN server :3478
            #   Fires in nat prerouting (dstnat-1 = -101), after mangle.
            #   Works for any destination IP: DNS-spoofed (192.168.1.1) OR real STUN IPs.
            redir_cmd = (
                f"nft insert rule inet passwall2 dstnat "
                f"ip saddr {device_ip} udp dport '{{ 3478, 3479, 19302 }}' "
                f"redirect to :3478 comment '\"stun_redir_{safe_ip}\"'"
            )
            r = subprocess.run(['/bin/sh', '-c', redir_cmd], capture_output=True, text=True)
            if r.returncode == 0:
                logger.info(f"nftables STUN redirect to :3478 added for {device_ip}")
            else:
                logger.warning(f"nft STUN redirect failed for {device_ip}: {r.stderr.strip()}")

            # Defense-in-depth: drop remaining STUN-related ports in fw4 forward
            drop_cmd = (
                f"nft add rule inet fw4 forward "
                f"ip saddr {device_ip} "
                f"udp dport '{{ 5349 }}' "
                f"drop comment '\"stun_drop_{safe_ip}\"'"
            )
            r = subprocess.run(['/bin/sh', '-c', drop_cmd], capture_output=True, text=True)
            if r.returncode == 0:
                logger.info(f"nftables STUN DROP rules added for {device_ip}")
        except Exception as e:
            logger.error(f"Error adding STUN nft rules for {device_ip}: {e}")

    def _add_doh_block_rules(self, device_ip: str) -> None:
        """Block DoH (DNS-over-HTTPS port 443) to known resolver IPs for *device_ip*.
        Rules are inserted into PSW2_MANGLE (prerouting mangle, priority -151), BEFORE
        the passwall2 catch-all TPROXY rule.  If placed in fw4 forward instead, they
        never fire because TPROXY already consumes the packets in prerouting.
        Dropping here forces Chrome/Firefox to fall back to plain UDP 53, which
        passwall2 redirects to the per-device dnsmasq → proxy DNS."""
        try:
            self._remove_doh_block_rules(device_ip)
            safe_ip = device_ip.replace('.', '_')
            doh_set = '{ ' + ', '.join(DOH_BLOCK_IPS) + ' }'
            # Drop TCP 443 (HTTPS DoH) and UDP 443 (QUIC/HTTP3 DoH) in PSW2_MANGLE
            # so the packets are discarded before xray TPROXY intercepts them.
            for proto in ('tcp', 'udp'):
                cmd = (
                    f"nft insert rule inet passwall2 PSW2_MANGLE "
                    f"ip saddr {device_ip} ip daddr '{doh_set}' "
                    f"{proto} dport 443 drop comment '\"doh_block_{safe_ip}\"'"
                )
                r = subprocess.run(['/bin/sh', '-c', cmd], capture_output=True, text=True)
                if r.returncode != 0:
                    logger.warning(f"nft DoH block ({proto}) in PSW2_MANGLE failed for {device_ip}: {r.stderr.strip()}")
            logger.info(f"DoH block rules added in PSW2_MANGLE for {device_ip}")
        except Exception as e:
            logger.error(f"Error adding DoH block rules for {device_ip}: {e}")

    def _remove_doh_block_rules(self, device_ip: str) -> None:
        """Remove DoH block nft rules for *device_ip* from PSW2_MANGLE and fw4 forward."""
        try:
            safe_ip = device_ip.replace('.', '_')
            comment = f'doh_block_{safe_ip}'
            # Clean from PSW2_MANGLE (current location) and fw4 forward (legacy location)
            for family, table, chain in [
                ('inet', 'passwall2', 'PSW2_MANGLE'),
                ('inet', 'fw4', 'forward'),
            ]:
                handles_out = subprocess.run(
                    ['/bin/sh', '-c',
                     f"nft -a list chain {family} {table} {chain} 2>/dev/null "
                     f"| grep '{comment}' | awk '{{print $NF}}'"],
                    capture_output=True, text=True
                ).stdout.strip()
                for handle in handles_out.splitlines():
                    handle = handle.strip()
                    if handle:
                        subprocess.run(
                            ['nft', 'delete', 'rule', family, table, chain, 'handle', handle],
                            capture_output=True
                        )
        except Exception as e:
            logger.debug(f"_remove_doh_block_rules({device_ip}): {e}")

    def _remove_stun_nft_rules(self, device_ip: str) -> None:
        """Remove all STUN nft rules for *device_ip* (bypass, redirect, drop)."""
        try:
            safe_ip = device_ip.replace('.', '_')
            # (table_family, table_name, chain, comment_substring)
            targets = [
                ('inet', 'passwall2', 'PSW2_MANGLE', f'stun_bypass_{safe_ip}'),
                ('inet', 'passwall2', 'dstnat',       f'stun_redir_{safe_ip}'),
                ('inet', 'fw4',       'forward',      f'stun_drop_{safe_ip}'),
                ('inet', 'fw4',       'forward',      f'stun_{safe_ip}'),  # legacy
            ]
            for family, table, chain, comment in targets:
                handles_out = subprocess.run(
                    ['/bin/sh', '-c',
                     f"nft -a list chain {family} {table} {chain} 2>/dev/null "
                     f"| grep '{comment}' | awk '{{print $NF}}'"],
                    capture_output=True, text=True
                ).stdout.strip()
                for handle in handles_out.splitlines():
                    handle = handle.strip()
                    if handle:
                        subprocess.run(
                            ['nft', 'delete', 'rule', family, table, chain, 'handle', handle],
                            capture_output=True
                        )
            logger.info(f"nftables STUN rules removed for {device_ip}")
        except Exception as e:
            logger.debug(f"_remove_stun_nft_rules({device_ip}): {e}")

    def _wait_for_passwall2_ready(self, timeout: int = 90) -> bool:
        """Poll /var/log/passwall2.log for 'Running complete!' written after the
        current restart.  Returns True when passwall2 signals it is ready."""
        log_path = '/var/log/passwall2.log'
        # Record current log size so we only scan new content
        try:
            baseline = int(
                subprocess.run(['wc', '-c', log_path], capture_output=True, text=True)
                .stdout.split()[0]
            )
        except Exception:
            baseline = 0

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            try:
                chunk = subprocess.run(
                    ['/bin/sh', '-c', f'tail -c +{baseline} {log_path} 2>/dev/null'],
                    capture_output=True, text=True
                ).stdout
                if 'Running complete!' in chunk:
                    logger.info("passwall2 is ready (Running complete!)")
                    return True
            except Exception:
                pass
        logger.warning("Timed out waiting for passwall2 to be ready")
        return False

    def _get_device_remote_fakedns(self, device_ip: str) -> bool:
        """Return True if remote_fakedns (Use proxy DNS) is enabled for this device."""
        try:
            cfg = self.run_uci_command(['show', self.config_name])
            current_section = None
            section_ip = None
            section_fakedns = False
            for line in cfg.splitlines():
                if '=acl_rule' in line:
                    if current_section and section_ip == device_ip:
                        return section_fakedns
                    current_section = line.split('=')[0].split('.', 1)[1]
                    section_ip = None
                    section_fakedns = False
                elif current_section:
                    if f'.{current_section}.sources=' in line:
                        section_ip = line.split('=', 1)[1].strip().strip('\'"')
                    elif f'.{current_section}.remote_fakedns=' in line:
                        section_fakedns = line.split('=', 1)[1].strip().strip('\'"') == '1'
            if current_section and section_ip == device_ip:
                return section_fakedns
        except Exception as e:
            logger.debug(f"_get_device_remote_fakedns({device_ip}): {e}")
        return False

    def _patch_xray_dns_through_proxy(self, device_ip: str) -> bool:
        """Patch the xray JSON config for device_ip so the original hostname is
        preserved end-to-end into the HTTP CONNECT request.  3proxy on the proxy
        server then resolves the hostname using its carrier (dongle) DNS, so
        browserleaks.com/dns shows only the carrier DNS.

        Strategy:
        1. Find the xray JSON whose dns-in inbound port matches the per-device
           dnsmasq upstream port (e.g. 11301).
        2. Set routing.domainStrategy = "AsIs" so xray does not resolve at routing
           time.
        3. On every inbound: enable sniffing with destOverride
           ["http","tls","fakedns","quic"], metadataOnly=false, routeOnly=false so
           the original hostname is recovered from FakeDNS / SNI / Host header and
           used as the destination.
        4. On the HTTP proxy outbound: ensure no domainStrategy: "UseIP*" leaks
           through (force "AsIs").
        5. Restore dns-out to its safe default (UDP 8.8.8.8 via direct, with
           hijack rules) in case a previous broken patch left it routed through
           the proxy.
        6. Kill + restart that xray process with the patched config."""
        try:
            import json as _json

            # Find the per-device dnsmasq upstream port
            acl_dir = self._get_acl_dir_for_device(device_ip)
            if not acl_dir:
                logger.warning(f"_patch_xray_dns: no ACL dir for {device_ip}")
                return False
            dnsmasq_conf = os.path.join(acl_dir, 'dnsmasq.conf')
            dns_port = None
            try:
                with open(dnsmasq_conf) as f:
                    for line in f:
                        m = re.match(r'server=127\.0\.0\.1#(\d+)', line.strip())
                        if m:
                            dns_port = int(m.group(1))
                            break
            except OSError:
                pass
            if not dns_port:
                logger.warning(f"_patch_xray_dns: cannot find dnsmasq upstream port for {device_ip}")
                return False

            # Find the xray JSON that owns this dns-in inbound port
            xray_json_dir = '/tmp/etc/passwall2/acl'
            target_json = None
            try:
                for fname in os.listdir(xray_json_dir):
                    if not fname.endswith('.json'):
                        continue
                    fpath = os.path.join(xray_json_dir, fname)
                    try:
                        with open(fpath) as f:
                            cfg = _json.load(f)
                        for ib in cfg.get('inbounds', []):
                            if ib.get('tag') == 'dns-in' and ib.get('port') == dns_port:
                                target_json = fpath
                                break
                    except Exception:
                        pass
                    if target_json:
                        break
            except OSError:
                pass

            if not target_json:
                logger.warning(f"_patch_xray_dns: no xray JSON with dns-in port {dns_port}")
                return False

            with open(target_json) as f:
                cfg = _json.load(f)

            # 1. routing.domainStrategy = AsIs
            cfg.setdefault('routing', {})['domainStrategy'] = 'AsIs'

            # 2. Enable hostname sniffing on all non-dns-in inbounds
            for ib in cfg.get('inbounds', []):
                if ib.get('tag') == 'dns-in':
                    continue
                ib['sniffing'] = {
                    'enabled': True,
                    'destOverride': ['http', 'tls', 'fakedns', 'quic'],
                    'metadataOnly': False,
                    'routeOnly': False,
                }

            # 3. Force domainStrategy=AsIs on every non-direct/blackhole/dns outbound
            #    and revert any previous proxySettings on dns-out.
            for ob in cfg.get('outbounds', []):
                proto = ob.get('protocol', '')
                tag = ob.get('tag', '')
                if tag == 'dns-out':
                    # Revert to safe defaults: UDP DNS direct with hijack rules
                    ob['settings'] = {
                        'port': 53,
                        'network': 'udp',
                        'address': '8.8.8.8',
                        'rules': [
                            {'qtype': '1,28', 'action': 'hijack'},
                            {'qtype': 65, 'action': 'reject'},
                            {'action': 'direct'},
                        ],
                    }
                    ob['proxySettings'] = {'tag': 'direct'}
                    continue
                if proto in ('freedom', 'blackhole', 'dns'):
                    continue
                # Proxy outbound: force AsIs so xray does not resolve hostname locally
                settings = ob.setdefault('settings', {})
                settings['domainStrategy'] = 'AsIs'

            # Write patched config
            with open(target_json, 'w') as f:
                _json.dump(cfg, f)

            # Kill old xray process for this config and restart it
            basename = os.path.basename(target_json)
            result = subprocess.run(
                ['/bin/sh', '-c',
                 f"ps | grep xray | grep '{basename}' | grep -v grep | awk '{{print $1}}'"],
                capture_output=True, text=True
            )
            for pid in result.stdout.strip().splitlines():
                pid = pid.strip()
                if pid:
                    subprocess.run(['kill', pid], capture_output=True)
            time.sleep(0.8)

            xray_bin = '/tmp/etc/passwall2/bin/xray'
            subprocess.Popen(
                [xray_bin, 'run', '-c', target_json],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"DNS patched through proxy for {device_ip} (port {dns_port}, sniffing+AsIs)")
            return True
        except Exception as e:
            logger.error(f"_patch_xray_dns_through_proxy({device_ip}): {e}")
            return False

    def _disable_lan_ipv6(self) -> bool:
        """Disable IPv6 on the LAN entirely: turn off DHCPv6 + RA, drop the LAN
        IPv6 address, and block IPv6 forwarding through the firewall.  Without
        this, IPv6 traffic from LAN devices bypasses passwall2's IPv4-only
        TPROXY and leaks DNS / IPs through the router's WAN6 path."""
        try:
            changed = False
            checks = [
                ('dhcp.lan.dhcpv6', 'disabled'),
                ('dhcp.lan.ra', 'disabled'),
                ('dhcp.lan.ndp', 'disabled'),
            ]
            for key, value in checks:
                cur = subprocess.run(['uci', 'get', key],
                                     capture_output=True, text=True).stdout.strip()
                if cur != value:
                    subprocess.run(['uci', 'set', f'{key}={value}'], check=False)
                    changed = True
            # Remove IPv6 address from LAN interface so devices don't autoconf via it
            cur_ip6 = subprocess.run(['uci', 'get', 'network.lan.ip6assign'],
                                     capture_output=True, text=True).stdout.strip()
            if cur_ip6:
                subprocess.run(['uci', 'delete', 'network.lan.ip6assign'], check=False)
                changed = True
            cur_ipaddr6 = subprocess.run(['uci', 'get', 'network.lan.ipaddr6'],
                                         capture_output=True, text=True).stdout.strip()
            if cur_ipaddr6:
                subprocess.run(['uci', 'delete', 'network.lan.ipaddr6'], check=False)
                changed = True
            if changed:
                subprocess.run(['uci', 'commit', 'dhcp'], check=False)
                subprocess.run(['uci', 'commit', 'network'], check=False)
                subprocess.run(['/etc/init.d/odhcpd', 'reload'],
                               capture_output=True)
                subprocess.run(['/etc/init.d/dnsmasq', 'reload'],
                               capture_output=True)
                logger.info("LAN IPv6 disabled (dhcpv6/ra/ndp off)")

            # Runtime: drop existing IPv6 address from br-lan and disable IPv6 in kernel
            subprocess.run(['/bin/sh', '-c',
                            "ip -6 addr flush dev br-lan scope global 2>/dev/null"],
                           capture_output=True)
            subprocess.run(['sysctl', '-w',
                            'net.ipv6.conf.br-lan.disable_ipv6=1'],
                           capture_output=True)
            subprocess.run(['sysctl', '-w',
                            'net.ipv6.conf.br-lan.accept_ra=0'],
                           capture_output=True)
            return True
        except Exception as e:
            logger.error(f"_disable_lan_ipv6: {e}")
            return False

    def _post_restart_inject_stun(self) -> None:
        """Background thread: wait for passwall2 to finish, then re-inject STUN DNS
        and nftables DROP rules for every currently registered device."""
        try:
            # Disable LAN IPv6 so devices can't leak DNS/traffic via WAN6 path
            self._disable_lan_ipv6()

            from router.stun_server import get_stun_server
            devices = get_stun_server().get_all()   # snapshot: {device_ip: proxy_ip}
            if not devices:
                return  # nothing to do

            if not self._wait_for_passwall2_ready():
                logger.warning("STUN post-restart injection skipped (passwall2 not ready)")
                return

            for device_ip in devices:
                logger.info(f"Post-restart: injecting STUN DNS + nft rules for {device_ip}")
                self._inject_stun_dns(device_ip)
                self._add_stun_nft_rules(device_ip)
                self._add_doh_block_rules(device_ip)
                if self._get_device_remote_fakedns(device_ip):
                    logger.info(f"Post-restart: patching xray DNS through proxy for {device_ip}")
                    self._patch_xray_dns_through_proxy(device_ip)
        except Exception as e:
            logger.error(f"_post_restart_inject_stun: {e}")

    def ensure_valid_main_nodes(self) -> bool:
        """Ensure main TCP/UDP nodes are set to valid existing nodes"""
        try:
            # Get all available nodes
            nodes = self.get_nodes()
            if not nodes:
                logger.info("No nodes available to set as main")
                return False
            
            # Use the first available node as default
            default_node = nodes[0]['section']
            logger.info(f"Using default node: {default_node}")
            
            # Get current config
            config = self.get_global_config()
            
            # Fix TCP node if invalid
            if not config.get('tcp_node_exists'):
                subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].tcp_node={default_node}'], check=False)
                logger.info(f"Fixed TCP node: {default_node}")
            
            # Fix UDP node if invalid
            if not config.get('udp_node_exists'):
                subprocess.run(['uci', 'set', f'{self.config_name}.@global[0].udp_node={default_node}'], check=False)
                logger.info(f"Fixed UDP node: {default_node}")
            
            # Commit changes
            subprocess.run(['uci', 'commit', self.config_name], check=False)
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring valid main nodes: {e}")
            return False