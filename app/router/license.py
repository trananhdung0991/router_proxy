"""
License Verification Module
Verifies software license with remote server
"""

import requests
import hashlib
import json
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LicenseManager:
    def __init__(self, license_key=None, server_url=None):
        """
        Initialize License Manager
        
        Args:
            license_key: Product license key
            server_url: License verification server URL
        """
        self.license_key = license_key or self._load_license_key()
        self.server_url = "https://routerlic.xproxy.io/api/verify-license"
        self.cache_file = "/tmp/license_cache.json"
        self.cache_duration = 3600  # Cache valid for 1 hour
        self.is_valid = False
        self.license_info = {}
        
    def _load_license_key(self):
        """Load license key from config file"""
        config_file = "/etc/license.key"
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    key = f.read().strip()
                    return key
            else:
                logger.warning("License file does not exist")
        except Exception as e:
            logger.error(f"Error reading license file: {e}")
        return None
    
    def _get_hardware_id(self):
        """Generate unique hardware ID from system info"""
        try:
            # Get MAC address
            import subprocess
            result = subprocess.run(['ip', 'link', 'show'], 
                                  capture_output=True, text=True, timeout=5)
            mac_info = result.stdout
            
            # Get serial number or other unique info
            serial = "UNKNOWN"
            if os.path.exists('/proc/cpuinfo'):
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'Serial' in line:
                            serial = line.split(':')[1].strip()
                            break
            
            # Create hardware ID hash
            hw_string = f"{mac_info}{serial}"
            hw_id = hashlib.sha256(hw_string.encode()).hexdigest()[:32]
            return hw_id
        except Exception as e:
            logger.error(f"Error getting hardware ID: {e}")
            return "DEFAULT_HW_ID"
    
    def _load_cache(self):
        """Load cached license verification"""
        if not os.path.exists(self.cache_file):
            return None
        
        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
            
            # Check if cache is expired
            cached_time = datetime.fromisoformat(cache.get('timestamp', ''))
            if datetime.now() - cached_time > timedelta(seconds=self.cache_duration):
                return None
            
            return cache
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return None
    
    def _save_cache(self, data):
        """Save license verification to cache"""
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def verify_license(self, force=False):
        """
        Verify license with server
        
        Args:
            force: Force verification even if cache exists
            
        Returns:
            bool: True if license is valid
        """
        # Check cache first
        if not force:
            cache = self._load_cache()
            if cache and cache.get('data', {}).get('valid'):
                self.is_valid = True
                self.license_info = cache.get('data', {})
                logger.info(f"License valid (cached): {self.license_info.get('product_name', 'Unknown')}")
                return True
        
        if not self.license_key:
            logger.warning("No license key found!")
            self.is_valid = False
            return False
        
        hw_id = self._get_hardware_id()
        
        try:
            # Send verification request to server
            payload = {
                'license_key': self.license_key,
                'hardware_id': hw_id,
                'product': 'router_proxy',
                'version': '1.0.0'
            }
            
            response = requests.post(
                self.server_url,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            logger.debug(f"HTTP status: {response.status_code}")
            try:
                data = response.json()
                logger.debug(f"Server response JSON: {json.dumps(data)[:1000]}")
            except Exception:
                logger.debug(f"Response text: {response.text}")
                data = {}

            if response.status_code == 200:
                
                if data.get('valid'):
                    self.is_valid = True
                    self.license_info = data
                    self._save_cache(data)
                    logger.info(f"License verified: {data.get('product_name', 'Unknown')}")
                    logger.info(f"Customer: {data.get('customer_name', 'Unknown')}")
                    logger.info(f"Expires: {data.get('expiry_date', 'Never')}")
                    if 'days_remaining' in data:
                        logger.info(f"Days remaining: {data['days_remaining']}")
                    return True
                else:
                    self.is_valid = False
                    logger.error(f"License invalid: {data.get('message', 'Unknown error')}")
                    return False
            else:
                logger.error(f"License server error: {response.status_code}")
                # If server is unreachable, check cache
                cache = self._load_cache()
                if cache and cache.get('data', {}).get('valid'):
                    logger.warning("Using cached license (server unreachable)")
                    self.is_valid = True
                    self.license_info = cache.get('data', {})
                    return True
                self.is_valid = False
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"License verification failed: {e}")
            # If network error, check cache
            cache = self._load_cache()
            if cache and cache.get('data', {}).get('valid'):
                logger.warning("Using cached license (network error)")
                self.is_valid = True
                self.license_info = cache.get('data', {})
                return True
            self.is_valid = False
            return False
    
    def check_license(self):
        """Quick license check - uses cache if available"""
        if self.is_valid:
            return True
        return self.verify_license(force=False)
    
    def get_license_info(self):
        """Get license information"""
        return self.license_info
    
    def is_license_valid(self):
        """Check if license is currently valid"""
        return self.is_valid


# Global license manager instance
_license_manager = None

def get_license_manager():
    """Get global license manager instance"""
    global _license_manager
    if _license_manager is None:
        _license_manager = LicenseManager()
    return _license_manager

def require_license(func):
    """Decorator to require valid license for function"""
    def wrapper(*args, **kwargs):
        lm = get_license_manager()
        if not lm.check_license():
            raise Exception("Valid license required to use this feature")
        return func(*args, **kwargs)
    return wrapper
