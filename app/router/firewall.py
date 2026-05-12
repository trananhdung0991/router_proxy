import subprocess
import logging
from typing import Optional, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class FirewallManager:
    """OpenWrt firewall management compatible with fw4/nftables"""
    
    def __init__(self):
        self.config_name = 'firewall'
        self._check_firewall_version()
    
    def _check_firewall_version(self):
        """Check if using fw4 (nftables) or fw3 (iptables)"""
        fw4_check = subprocess.run(['which', 'fw4'], capture_output=True)
        self.use_fw4 = fw4_check.returncode == 0
        logger.info(f"Using firewall version: {'fw4 (nftables)' if self.use_fw4 else 'fw3 (iptables)'}")
    
    def run_uci_command(self, cmd: list) -> str:
        """Execute UCI command and return output"""
        try:
            result = subprocess.run(['uci'] + cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if 'delete' in cmd and ('not found' in e.stderr.lower() or 'no such file' in e.stderr.lower()):
                logger.debug(f"UCI delete: section not found (normal): {' '.join(cmd)}")
                return ""
            logger.error(f"UCI command failed: {e}")
            logger.debug(f"Command: {' '.join(cmd)}")
            logger.error(f"Error: {e.stderr}")
            return ""
    
    def set_client_transparent_proxy(self, client_ip: str, proxy_url: str) -> bool:
        """Set up client traffic redirection"""
        try:
            parsed = urlparse(proxy_url)
            if not parsed.hostname or not parsed.port:
                logger.error(f"Invalid proxy URL: {proxy_url}")
                return False
            
            proxy_host = parsed.hostname
            proxy_port = str(parsed.port)
            
            logger.info(f"Setting up firewall redirect: {client_ip} -> {proxy_host}:{proxy_port}")
            
            # Remove existing rules first
            self.clear_client_rules(client_ip)
            
            if self.use_fw4:
                # Use nftables-compatible rules for fw4
                return self._add_nftables_rules(client_ip, proxy_host, proxy_port)
            else:
                # Use iptables-compatible rules for fw3
                return self._add_iptables_rules(client_ip, proxy_host, proxy_port)
            
        except Exception as e:
            logger.error(f"Error setting client transparent proxy: {e}")
            return False
    
    def _add_nftables_rules(self, client_ip: str, proxy_host: str, proxy_port: str) -> bool:
        """Add nftables rules using fw4"""
        try:
            rule_base = f"proxy_{client_ip.replace('.', '_')}"
            
            # Create DNAT rules for HTTP/HTTPS traffic
            commands = [
                # Rule for HTTP (port 80)
                ['set', f'{self.config_name}.{rule_base}_http=rule'],
                ['set', f'{self.config_name}.{rule_base}_http.name=Proxy HTTP {client_ip}'],
                ['set', f'{self.config_name}.{rule_base}_http.src=lan'],
                ['set', f'{self.config_name}.{rule_base}_http.src_ip={client_ip}'],
                ['set', f'{self.config_name}.{rule_base}_http.dest_port=80'],
                ['set', f'{self.config_name}.{rule_base}_http.proto=tcp'],
                ['set', f'{self.config_name}.{rule_base}_http.target=ACCEPT'],
                
                # Rule for HTTPS (port 443) 
                ['set', f'{self.config_name}.{rule_base}_https=rule'],
                ['set', f'{self.config_name}.{rule_base}_https.name=Proxy HTTPS {client_ip}'],
                ['set', f'{self.config_name}.{rule_base}_https.src=lan'],
                ['set', f'{self.config_name}.{rule_base}_https.src_ip={client_ip}'],
                ['set', f'{self.config_name}.{rule_base}_https.dest_port=443'],
                ['set', f'{self.config_name}.{rule_base}_https.proto=tcp'],
                ['set', f'{self.config_name}.{rule_base}_https.target=ACCEPT'],
            ]
            
            # Execute UCI commands
            for cmd in commands:
                result = self.run_uci_command(cmd)
            
            # Commit changes
            self.run_uci_command(['commit', self.config_name])
            
            # Reload firewall
            reload_result = subprocess.run(['service', 'firewall', 'reload'], 
                                         capture_output=True, text=True)
            if reload_result.returncode != 0:
                logger.error(f"Firewall reload failed: {reload_result.stderr}")
                return False
            
            logger.info(f"Successfully added nftables rules for {client_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding nftables rules: {e}")
            return False
    
    def _add_iptables_rules(self, client_ip: str, proxy_host: str, proxy_port: str) -> bool:
        """Add iptables rules using fw3 (legacy)"""
        try:
            rule_base = f"proxy_{client_ip.replace('.', '_')}"
            
            # Create redirect rules
            commands = [
                # Redirect rule for HTTP/HTTPS
                ['set', f'{self.config_name}.{rule_base}=redirect'],
                ['set', f'{self.config_name}.{rule_base}.name=Proxy redirect {client_ip}'],
                ['set', f'{self.config_name}.{rule_base}.src=lan'],
                ['set', f'{self.config_name}.{rule_base}.src_ip={client_ip}'],
                ['set', f'{self.config_name}.{rule_base}.dest_ip={proxy_host}'],
                ['set', f'{self.config_name}.{rule_base}.dest_port={proxy_port}'],
                ['set', f'{self.config_name}.{rule_base}.target=DNAT'],
                ['set', f'{self.config_name}.{rule_base}.proto=tcp'],
            ]
            
            for cmd in commands:
                self.run_uci_command(cmd)
            
            self.run_uci_command(['commit', self.config_name])
            subprocess.run(['service', 'firewall', 'reload'], check=False)
            
            logger.info(f"Successfully added iptables rules for {client_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding iptables rules: {e}")
            return False
    
    def clear_client_rules(self, client_ip: str) -> bool:
        """Remove all firewall rules for client"""
        try:
            rule_prefix = f"proxy_{client_ip.replace('.', '_')}"
            
            # Get all firewall sections
            result = self.run_uci_command(['show', self.config_name])
            
            sections_to_delete = []
            for line in result.split('\n'):
                if rule_prefix in line and '=' in line:
                    section = line.split('=')[0].split('.')[1]
                    if section not in sections_to_delete:
                        sections_to_delete.append(section)
            
            # Delete matching sections
            for section in sections_to_delete:
                self.run_uci_command(['delete', f'{self.config_name}.{section}'])
            
            if sections_to_delete:
                self.run_uci_command(['commit', self.config_name])
                subprocess.run(['service', 'firewall', 'reload'], check=False)
                logger.info(f"Cleared {len(sections_to_delete)} firewall rules for {client_ip}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error clearing client rules: {e}")
            return False
    
    def get_client_rules(self, client_ip: str) -> list:
        """Get all firewall rules for a specific client"""
        try:
            rule_prefix = f"proxy_{client_ip.replace('.', '_')}"
            result = self.run_uci_command(['show', self.config_name])
            
            client_rules = []
            for line in result.split('\n'):
                if rule_prefix in line:
                    client_rules.append(line)
            
            return client_rules
            
        except Exception as e:
            logger.error(f"Error getting client rules: {e}")
            return []