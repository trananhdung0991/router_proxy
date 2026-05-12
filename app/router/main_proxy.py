import subprocess
import threading
import time
import os
import signal
import logging
from typing import Optional

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TinyproxyP:
    def __init__(self, host='0.0.0.0', port=4001, username=None, password=None):
        """
        Tinyproxy HTTP proxy wrapper
        
        Args:
            host: Bind address (default: 0.0.0.0)
            port: Bind port (default: 4001)
            username: Optional username for authentication
            password: Optional password for authentication
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.process = None
        self.running = False
        self.config_file = f'/tmp/tinyproxy_{port}.conf'
        
    def create_config(self):
        """Create tinyproxy configuration file"""
        try:
            # Simple configuration compatible with modern tinyproxy
            config = f"""Port {self.port}
Listen {self.host}
Timeout 600
Logfile "/tmp/tinyproxy_{self.port}.log"
LogLevel Info
PidFile "/tmp/tinyproxy_{self.port}.pid"
MaxClients 100
MaxRequestsPerChild 0
Allow 127.0.0.1
Allow 192.168.0.0/16
Allow 10.0.0.0/8
ConnectPort 443
ConnectPort 563
"""
            
            # Add authentication if provided
            if self.username and self.password:
                auth_file = f'/tmp/tinyproxy_{self.port}.auth'
                with open(auth_file, 'w') as f:
                    f.write(f"{self.username}:{self.password}\n")
                config += f"BasicAuth {auth_file}\n"
            
            with open(self.config_file, 'w') as f:
                f.write(config)
                
            logger.info(f"Created tinyproxy config: {self.config_file}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create tinyproxy config: {e}")
            return False
    
    def _kill_existing_tinyproxy(self):
        """Kill any existing tinyproxy processes on this port"""
        try:
            # Try to kill via PID file first
            pid_file = f'/tmp/tinyproxy_{self.port}.pid'
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.5)
                    logger.info(f"Killed existing tinyproxy process {pid}")
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
                finally:
                    try:
                        os.remove(pid_file)
                    except:
                        pass
            
            # Also try pkill as backup
            try:
                subprocess.run(['pkill', '-f', f'tinyproxy.*{self.port}'], 
                             check=False, capture_output=True, timeout=2)
                time.sleep(0.5)
            except:
                pass
                
        except Exception as e:
            logger.warning(f"Error killing existing tinyproxy: {e}")
        
    def start(self) -> bool:
        """Start the tinyproxy HTTP proxy"""
        try:
            # Kill any existing tinyproxy on this port first
            self._kill_existing_tinyproxy()
            
            # Create configuration
            if not self.create_config():
                logger.error("Cannot start proxy: config creation failed")
                return False
                
            # Start tinyproxy process without -d flag (let it daemonize)
            cmd = ['tinyproxy', '-c', self.config_file]
            
            logger.info(f"Starting tinyproxy on {self.host}:{self.port}")
            if self.username and self.password:
                logger.info(f"Starting tinyproxy with authentication")
            else:
                logger.info(f"Starting tinyproxy without authentication")
                
            # Start tinyproxy process
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            # Give it a moment to start
            time.sleep(1)
            
            # Check if tinyproxy is actually running by checking PID file
            pid_file = f'/tmp/tinyproxy_{self.port}.pid'
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    # Verify the process is actually running
                    os.kill(pid, 0)  # Doesn't kill, just checks if process exists
                    self.running = True
                    # Store PID for reference
                    class ProcessInfo:
                        def __init__(self, pid):
                            self.pid = pid
                    self.process = ProcessInfo(pid)
                    logger.info(f"Tinyproxy started successfully (PID: {pid})")
                    return True
                except (ValueError, ProcessLookupError, PermissionError, FileNotFoundError):
                    logger.error(f"Tinyproxy PID file exists but process not running")
                    return False
            else:
                # Check stderr for actual errors (ignore warnings)
                if result.stderr and 'error' in result.stderr.lower():
                    logger.error(f"Tinyproxy failed to start: {result.stderr}")
                elif result.stderr:
                    logger.warning(f"Tinyproxy started with warnings: {result.stderr}")
                return False
                
        except FileNotFoundError:
            logger.error("Tinyproxy not found. Please install it first: opkg install tinyproxy")
            return False
        except Exception as e:
            logger.error(f"Error starting tinyproxy: {e}")
            return False
            
    def _monitor_process(self):
        """Monitor the tinyproxy process"""
        try:
            while self.running and self.process:
                # Check if process is still alive
                if not self.is_running():
                    logger.error(f"Tinyproxy process (PID: {self.process.pid}) has died")
                    self.running = False
                    break
                time.sleep(5)  # Check every 5 seconds
        except Exception as e:
            logger.error(f"Error monitoring process: {e}")
            
    def stop(self):
        """Stop the tinyproxy proxy"""
        try:
            if self.process and self.running:
                logger.info("Stopping tinyproxy proxy...")
                self.running = False
                
                # Kill the process using the PID
                try:
                    os.kill(self.process.pid, signal.SIGTERM)
                    time.sleep(1)
                    # Check if it's still running
                    try:
                        os.kill(self.process.pid, 0)
                        # Still running, force kill
                        logger.warning("Tinyproxy didn't stop gracefully, force killing...")
                        os.kill(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Already dead
                except ProcessLookupError:
                    pass  # Already dead
                    
                logger.info("Tinyproxy proxy stopped")
                self.process = None
                
            # Clean up config files
            try:
                if os.path.exists(self.config_file):
                    os.remove(self.config_file)
                auth_file = f'/tmp/tinyproxy_{self.port}.auth'
                if os.path.exists(auth_file):
                    os.remove(auth_file)
                pid_file = f'/tmp/tinyproxy_{self.port}.pid'
                if os.path.exists(pid_file):
                    os.remove(pid_file)
                    os.remove(auth_file)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Error stopping tinyproxy: {e}")
            
    def is_running(self) -> bool:
        """Check if the proxy is running"""
        if not self.running or not self.process:
            return False
        
        # Check if process is still alive via PID file and process check
        try:
            pid_file = f'/tmp/tinyproxy_{self.port}.pid'
            if os.path.exists(pid_file):
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # Check if process exists
                return True
        except (FileNotFoundError, ProcessLookupError, ValueError, PermissionError):
            pass
        
        self.running = False
        return False
        
    def get_status(self) -> dict:
        """Get proxy status information"""
        return {
            'running': self.is_running(),
            'host': self.host,
            'port': self.port,
            'pid': self.process.pid if self.process else None,
            'has_auth': bool(self.username and self.password),
            'proxy_url': self._get_proxy_url()
        }
        
    def _get_proxy_url(self) -> str:
        """Get the proxy URL"""
        if self.username and self.password:
            return f"http://{self.username}:{self.password}@{self.host}:{self.port}"
        else:
            return f"http://{self.host}:{self.port}"

class TinyproxyMultiManager:
    """Manage multiple tinyproxy instances """
    
    def __init__(self):
        self.proxies = {}
        
    def create_proxy(self, name: str, host='127.0.0.1', port=4001, username=None, password=None) -> 'TinyproxyP':
        """Create a new tinyproxy instance"""
        if name in self.proxies:
            logger.warning(f"Proxy '{name}' already exists")
            return self.proxies[name]
            
        proxy = TinyproxyP(host, port, username, password)
        self.proxies[name] = proxy
        return proxy
        
    def start_proxy(self, name: str) -> bool:
        """Start a specific proxy"""
        if name not in self.proxies:
            logger.error(f"Proxy '{name}' not found")
            return False
            
        return self.proxies[name].start()
        
    def stop_proxy(self, name: str):
        """Stop a specific proxy"""
        if name in self.proxies:
            self.proxies[name].stop()
            
    def stop_all(self):
        """Stop all proxies"""
        for proxy in self.proxies.values():
            proxy.stop()
            
    def get_proxy(self, name: str) -> Optional['TinyproxyP']:
        """Get a proxy instance by name"""
        return self.proxies.get(name)
        
    def list_proxies(self) -> dict:
        """List all proxies and their status"""
        return {name: proxy.get_status() for name, proxy in self.proxies.items()}
