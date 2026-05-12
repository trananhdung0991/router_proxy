"""
OpenWrt Router Configuration Utilities
Handles router IP configuration and network management
"""

import subprocess
import ipaddress
import json
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class OpenWrtRouterManager:
    """Manages OpenWrt router configuration"""
    
    def __init__(self):
        self.interface = "lan"  # Default LAN interface
        
    def get_current_config(self) -> Dict:
        """Get current router configuration"""
        try:
            config = {}
            
            # Get router IP
            result = self._run_uci_command(['uci', 'get', 'network.lan.ipaddr'])
            if result[0]:
                config['routerIP'] = result[1].strip()
            else:
                raise Exception("Failed to get router IP")
            
            # Get netmask
            result = self._run_uci_command(['uci', 'get', 'network.lan.netmask'])
            config['netmask'] = result[1].strip() if result[0] else "255.255.255.0"
            
            # Get interface
            config['interface'] = self.interface
            
            # Get DHCP configuration
            dhcp_config = self._get_dhcp_config(config['routerIP'])
            config.update(dhcp_config)
            
            return config
            
        except Exception as e:
            raise Exception(f"Failed to get router configuration: {str(e)}")
    
    def change_router_ip(self, new_ip: str, netmask: str = "255.255.255.0", 
                        dhcp_start: str = None, dhcp_end: str = None) -> bool:
        """Change router IP address and related configuration"""
        try:
            # Validate IP addresses
            self._validate_ip(new_ip)
            self._validate_ip(netmask)
            
            # Set new router IP
            success, output = self._run_uci_command(['uci', 'set', f'network.lan.ipaddr={new_ip}'])
            if not success:
                raise Exception(f"Failed to set router IP: {output}")
            
            # Set netmask
            self._run_uci_command(['uci', 'set', f'network.lan.netmask={netmask}'])
            
            # Update DHCP configuration if provided
            if dhcp_start and dhcp_end:
                self._update_dhcp_config(new_ip, dhcp_start, dhcp_end)
            
            # Commit changes
            success, output = self._run_uci_command(['uci', 'commit'])
            if not success:
                raise Exception(f"Failed to commit changes: {output}")
            
            # Restart network service
            self._restart_network_service()
            
            return True
            
        except Exception as e:
            raise Exception(f"Failed to change router IP: {str(e)}")
    
    def test_ip_availability(self, ip: str) -> Tuple[bool, str]:
        """Test if an IP address is available"""
        try:
            self._validate_ip(ip)
            
            # Test with ping
            result = subprocess.run(['ping', '-c', '1', '-W', '2', ip], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return False, f"IP {ip} is already in use"
            else:
                return True, f"IP {ip} appears to be available"
                
        except Exception as e:
            return False, f"Error testing IP: {str(e)}"
    
    def _get_dhcp_config(self, router_ip: str) -> Dict:
        """Get DHCP configuration"""
        dhcp_config = {
            'dhcpStart': '',
            'dhcpEnd': ''
        }
        
        try:
            # Get DHCP start offset
            success, start_output = self._run_uci_command(['uci', 'get', 'dhcp.lan.start'])
            success2, limit_output = self._run_uci_command(['uci', 'get', 'dhcp.lan.limit'])
            
            if success and success2:
                start_offset = int(start_output.strip())
                limit = int(limit_output.strip())
                
                # Calculate DHCP range
                router_parts = router_ip.split('.')
                base_ip = '.'.join(router_parts[:3])
                
                dhcp_config['dhcpStart'] = f"{base_ip}.{start_offset}"
                dhcp_config['dhcpEnd'] = f"{base_ip}.{start_offset + limit - 1}"
                
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to get DHCP config: {e}")
        
        return dhcp_config
    
    def _update_dhcp_config(self, router_ip: str, dhcp_start: str, dhcp_end: str):
        """Update DHCP configuration"""
        try:
            # Calculate DHCP parameters
            router_parts = router_ip.split('.')
            start_parts = dhcp_start.split('.')
            end_parts = dhcp_end.split('.')
            
            start_offset = int(start_parts[3])
            end_offset = int(end_parts[3])
            limit = end_offset - start_offset + 1
            
            # Set DHCP configuration
            self._run_uci_command(['uci', 'set', f'dhcp.lan.start={start_offset}'])
            self._run_uci_command(['uci', 'set', f'dhcp.lan.limit={limit}'])
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to update DHCP config: {e}")
    
    def _restart_network_service(self):
        """Restart network service"""
        try:
            subprocess.run(['service', 'network', 'restart'], 
                          capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("Network service restart timed out")
        except Exception as e:
            logger.warning(f"Network service restart failed: {e}")
    
    def _run_uci_command(self, command: list, timeout: int = 10) -> Tuple[bool, str]:
        """Run UCI command and return success status and output"""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout
        except subprocess.TimeoutExpired:
            return False, "Command timeout"
        except Exception as e:
            return False, str(e)
    
    def _validate_ip(self, ip: str):
        """Validate IP address format"""
        try:
            ipaddress.IPv4Address(ip)
        except ipaddress.AddressValueError:
            raise ValueError(f"Invalid IP address: {ip}")
    
    def get_network_interfaces(self) -> list:
        """Get available network interfaces"""
        try:
            result = subprocess.run(['uci', 'show', 'network'], 
                                  capture_output=True, text=True, timeout=10)
            
            interfaces = []
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if '.proto=' in line and 'static' in line:
                        interface = line.split('.')[1]
                        if interface not in interfaces:
                            interfaces.append(interface)
            
            return interfaces if interfaces else ['lan']
            
        except Exception as e:
            logger.warning(f"Failed to get interfaces: {e}")
            return ['lan']
    
    def backup_current_config(self) -> Dict:
        """Backup current configuration for rollback"""
        try:
            return self.get_current_config()
        except Exception as e:
            logger.warning(f"Failed to backup config: {e}")
            return {}
    
    def restore_config(self, config: Dict) -> bool:
        """Restore configuration from backup"""
        try:
            if 'routerIP' in config:
                return self.change_router_ip(
                    config['routerIP'],
                    config.get('netmask', '255.255.255.0'),
                    config.get('dhcpStart'),
                    config.get('dhcpEnd')
                )
            return False
        except Exception as e:
            logger.error(f"Error restoring config: {e}")
            return False