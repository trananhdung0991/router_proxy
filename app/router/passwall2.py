import subprocess
import time
import random
import string
import re
import logging
from typing import Dict, List, Optional

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

    def set_client_proxy_rule(self, client_ip: str, node_section: str, remote_fakedns: bool = False) -> bool:
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
            logger.info(f"Restarting Passwall2 to apply rule for {client_ip}")
            self._restart_passwall2()

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