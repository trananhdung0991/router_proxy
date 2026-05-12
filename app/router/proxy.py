from router.passwall2 import Passwall2Manager
from router.firewall import FirewallManager
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List
import subprocess
import json
import time
import os
import logging
from .db.clients import ClientsDB  # This should now work

# Set up logging
logger = logging.getLogger(__name__)

class ProxyManager:
    def __init__(self, db):
        self.client_proxy_db = db.clients_db
        try:
            self.passwall2 = Passwall2Manager()
        except Exception as e:
            logger.warning(f"Failed to initialize Passwall2Manager: {e}")
            self.passwall2 = None
        
        try:
            self.firewall = FirewallManager()
        except Exception as e:
            logger.warning(f"Failed to initialize FirewallManager: {e}")
            self.firewall = None

        """Initialize the ProxyManager with database connection"""
        self.proxy_rules = {}
        self.active_proxies = {}

    def set_client_proxy(self, ip: str, proxy_url: str, hostname: str = '', remote_fakedns: bool = False, proxy_type: str = 'HTTP') -> bool:
        """Set proxy for client with optional remote_fakedns"""
        try:
            if not proxy_url or proxy_url.strip() == "":
                # Remove proxy
                logger.info(f"Removing proxy for client: {ip}")
                success = self.passwall2.remove_client_proxy_rule(ip)
                if success:
                    # Clear all settings including remote_fakedns
                    self.client_proxy_db.save_client(ip, None, hostname, "", False, 'HTTP')
                    logger.info(f"Successfully saved to database: {ip} -> (cleared)")
                return success
            else:
                # Set proxy
                proxy_info = self.parse_proxy_url(proxy_url, proxy_type)
                if not proxy_info:
                    logger.error(f"Failed to parse proxy URL: {proxy_url}")
                    return False

                # Create node name
                clean_server = proxy_info['server'].replace('.', '_')
                node_name = f"{hostname}_{clean_server}_{proxy_info['port']}"

                # Add proxy node
                node_section = self.passwall2.add_proxy_node(
                    name=node_name,
                    server=proxy_info['server'],
                    port=int(proxy_info['port']),
                    protocol=proxy_info['protocol'],
                    username=proxy_info['username'],
                    password=proxy_info['password']
                )

                if not node_section:
                    logger.error(f"Failed to create proxy node for {ip}")
                    return False

                # Set ACL rule with remote_fakedns option and proxy server IP (for STUN spoofing)
                success = self.passwall2.set_client_proxy_rule(
                    ip, node_section, remote_fakedns, proxy_info['server']
                )
                if success:
                    # Save to database including remote_fakedns setting
                    self.client_proxy_db.save_client(ip, None, hostname, proxy_url, remote_fakedns, proxy_type)
                    logger.info(f"Successfully saved to database: {ip} -> {proxy_url}, remote_fakedns: {remote_fakedns}")
                
                return success

        except Exception as e:
            logger.error(f"Error setting client proxy: {e}")
            return False

    def get_all_client_proxies(self) -> dict:
        """Get all client proxy configurations from database"""
        try:
            return self.client_proxy_db.get_all_clients()
        except Exception as e:
            logger.error(f"Error getting all client proxies: {e}")
            return {}

    def parse_proxy_url(self, proxy_url: str, proxy_type: str = 'HTTP') -> Optional[Dict[str, str]]:
        """Parse proxy URL and extract components"""
        try:
            if not proxy_url or proxy_url.strip() == "":
                return None
                
            proxy_url = proxy_url.strip()
            proxy_type = proxy_type.upper()
            
            # Handle different proxy URL formats
            if proxy_url.startswith('socks5://'):
                # Parse: socks5://username:password@host:port or socks5://host:port
                url_without_scheme = proxy_url[9:]  # Remove 'socks5://'
                
                if '@' in url_without_scheme:
                    # Format: username:password@host:port
                    auth_part, host_port = url_without_scheme.split('@', 1)
                    if ':' in auth_part:
                        username, password = auth_part.split(':', 1)
                    else:
                        username = auth_part
                        password = ''
                else:
                    # Format: host:port (no authentication)
                    host_port = url_without_scheme
                    username = ''
                    password = ''
                
                # Parse host:port
                if ':' in host_port:
                    host, port_str = host_port.rsplit(':', 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        logger.error(f"Invalid port in SOCKS5 URL: {port_str}")
                        return None
                else:
                    host = host_port
                    port = 1080  # Default SOCKS5 port
                
                return {
                    'protocol': 'socks5',
                    'server': host,
                    'port': str(port),
                    'username': username,
                    'password': password
                }
                
            elif proxy_url.startswith('socks4://'):
                # Parse: socks4://host:port
                url_without_scheme = proxy_url[9:]  # Remove 'socks4://'
                
                if ':' in url_without_scheme:
                    host, port_str = url_without_scheme.rsplit(':', 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        logger.error(f"Invalid port in SOCKS4 URL: {port_str}")
                        return None
                else:
                    host = url_without_scheme
                    port = 1080  # Default SOCKS port
                
                return {
                    'protocol': 'socks4',
                    'server': host,
                    'port': str(port),
                    'username': '',
                    'password': ''
                }
                
            elif proxy_url.startswith('http://'):
                # Parse: http://username:password@host:port or http://host:port
                url_without_scheme = proxy_url[7:]  # Remove 'http://'
                
                if '@' in url_without_scheme:
                    # Format: username:password@host:port
                    auth_part, host_port = url_without_scheme.split('@', 1)
                    if ':' in auth_part:
                        username, password = auth_part.split(':', 1)
                    else:
                        username = auth_part
                        password = ''
                else:
                    # Format: host:port (no authentication)
                    host_port = url_without_scheme
                    username = ''
                    password = ''
                
                # Parse host:port
                if ':' in host_port:
                    host, port_str = host_port.rsplit(':', 1)
                    try:
                        port = int(port_str)
                    except ValueError:
                        logger.error(f"Invalid port in HTTP URL: {port_str}")
                        return None
                else:
                    host = host_port
                    port = 8080  # Default HTTP proxy port
                
                return {
                    'protocol': 'http',
                    'server': host,
                    'port': str(port),
                    'username': username,
                    'password': password
                }
                
            else:
                # Parse scheme-less format: username:password@host:port or host:port
                username = ''
                password = ''
                
                if '@' in proxy_url:
                    # Format: username:password@host:port
                    auth_part, host_port = proxy_url.split('@', 1)
                    if ':' in auth_part:
                        username, password = auth_part.split(':', 1)
                    else:
                        username = auth_part
                        password = ''
                else:
                    # Format: host:port (no authentication)
                    host_port = proxy_url
                
                # Parse host:port
                if ':' in host_port:
                    host, port_str = host_port.rsplit(':', 1)
                    try:
                        port = int(port_str)
                        # Use the proxy_type parameter instead of assuming HTTP
                        protocol = 'socks5' if proxy_type == 'SOCKS5' else 'http'
                        return {
                            'protocol': protocol,
                            'server': host,
                            'port': str(port),
                            'username': username,
                            'password': password
                        }
                    except ValueError:
                        logger.error(f"Invalid port in proxy URL: {port_str}")
                        return None
                else:
                    logger.error(f"Invalid proxy URL format: {proxy_url}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error parsing proxy URL '{proxy_url}': {e}")
            return None