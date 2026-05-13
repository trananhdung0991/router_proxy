import sqlite3
import json
import os
import logging
from typing import Dict, List, Optional, Any
from .db import DB
from flask import jsonify

logger = logging.getLogger(__name__)

class ClientsDB:
    def __init__(self, db: DB):
        self.db = db
        self.init_database()
    
    def init_database(self):
        """Initialize the database tables"""
        try:
            # Use self.db.ensure_table for table creation
            self.db.ensure_table('clients', '''
                ip TEXT PRIMARY KEY,
                hostname TEXT,
                mac TEXT,
                proxy TEXT,
                proxy_type TEXT DEFAULT "HTTP",
                remote_fakedns BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ''')
            
            # Migration: Add proxy_type column if it doesn't exist
            try:
                self.db.execute('''
                    ALTER TABLE clients ADD COLUMN proxy_type TEXT DEFAULT "HTTP"
                ''')
                logger.info("Added proxy_type column to clients table")
            except Exception as e:
                # Column already exists, which is fine
                if "duplicate column name" not in str(e).lower():
                    logger.debug(f"proxy_type column migration: {e}")

            # Migration: Add exit_ip column if it doesn't exist
            try:
                self.db.execute('''
                    ALTER TABLE clients ADD COLUMN exit_ip TEXT DEFAULT ""
                ''')
                logger.info("Added exit_ip column to clients table")
            except Exception as e:
                if "duplicate column name" not in str(e).lower():
                    logger.debug(f"exit_ip column migration: {e}")
            
            logger.info("Database initialized")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
    
    def get_all_clients(self) -> Dict[str, Dict[str, Any]]:
        """Get all client configurations"""
        try:
            # Use self.db.query_all
            rows = self.db.query_all('''
                SELECT ip, hostname, mac, proxy, proxy_type, remote_fakedns, exit_ip, created_at, updated_at
                FROM clients
            ''')
            # Convert to dictionary with IP as key
            clients = {}
            for row in rows:
                clients[row['ip']] = {
                    'ip': row['ip'],
                    'hostname': row['hostname'] or '',
                    'mac': row['mac'] or '',
                    'proxy': row['proxy'] or '',
                    'proxy_type': row['proxy_type'] or 'HTTP',
                    'remote_fakedns': bool(row['remote_fakedns']),
                    'exit_ip': row['exit_ip'] or '',
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
            return clients
            
        except Exception as e:
            logger.error(f"Error getting all clients: {e}")
            return {}
    
    def get_client(self, ip: str) -> Optional[Dict[str, Any]]:
        """Get a specific client by IP"""
        try:
            # Use self.db.query_one
            row = self.db.query_one('''
                SELECT ip, hostname, mac, proxy, proxy_type, remote_fakedns, exit_ip, created_at, updated_at
                FROM clients
                WHERE ip = ?
            ''', (ip,))
            
            if row:
                return {
                    'ip': row['ip'],
                    'hostname': row['hostname'] or '',
                    'mac': row['mac'] or '',
                    'proxy': row['proxy'] or '',
                    'proxy_type': row['proxy_type'] or 'HTTP',
                    'remote_fakedns': bool(row['remote_fakedns']),
                    'exit_ip': row['exit_ip'] or '',
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting client {ip}: {e}")
            return None
    
    def save_client(self, ip: str, hostname: str = "", mac: str = "", proxy: str = "", remote_fakedns: bool = False, proxy_type: str = 'HTTP', exit_ip: str = '') -> bool:
        """Save or update a client configuration"""
        try:
            # Use self.db.upsert_row for INSERT OR REPLACE functionality
            data = {
                'ip': ip,
                'hostname': hostname,
                'mac': mac,
                'proxy': proxy,
                'proxy_type': proxy_type.upper() if proxy_type else 'HTTP',
                'remote_fakedns': remote_fakedns,
                'exit_ip': exit_ip,
                'updated_at': 'CURRENT_TIMESTAMP'
            }
            
            # First try to use upsert_row
            try:
                self.db.upsert_row('clients', 'ip', data)
            except:
                # Fallback to manual INSERT OR REPLACE
                self.db.execute('''
                    INSERT OR REPLACE INTO clients 
                    (ip, hostname, mac, proxy, proxy_type, remote_fakedns, exit_ip, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (ip, hostname, mac, proxy, proxy_type.upper() if proxy_type else 'HTTP', remote_fakedns, exit_ip))
            
            logger.info(f"Client saved: {ip} -> {proxy} (exit_ip: {exit_ip})")
            return True
            
        except Exception as e:
            logger.error(f"Error saving client {ip}: {e}")
            return False
    
    def delete_client(self, ip: str) -> bool:
        """Delete a client configuration"""
        try:
            # Use self.db.delete
            self.db.delete('clients', 'ip = ?', (ip,))
            
            logger.info(f"Client deleted: {ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting client {ip}: {e}")
            return False
    
    def update_remote_fakedns(self, ip: str, remote_fakedns: bool) -> bool:
        """Update only the remote_fakedns setting for a client"""
        try:
            # Use self.db.update
            data = {
                'remote_fakedns': remote_fakedns,
                'updated_at': 'CURRENT_TIMESTAMP'
            }
            
            # Check if client exists first
            existing = self.get_client(ip)
            if not existing:
                logger.warning(f"No client found with IP {ip}")
                return False
            
            # Use execute for CURRENT_TIMESTAMP to work properly
            self.db.execute('''
                UPDATE clients 
                SET remote_fakedns = ?, updated_at = CURRENT_TIMESTAMP
                WHERE ip = ?
            ''', (remote_fakedns, ip))
            
            logger.info(f"Remote FakeDNS updated for {ip}: {remote_fakedns}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating remote_fakedns for {ip}: {e}")
            return False
    
    def get_clients_with_proxy(self) -> Dict[str, Dict[str, Any]]:
        """Get only clients that have proxy configured"""
        try:
            # Use self.db.query_all
            rows = self.db.query_all('''
                SELECT ip, hostname, mac, proxy, proxy_type, remote_fakedns, created_at, updated_at
                FROM clients
                WHERE proxy IS NOT NULL AND proxy != ''
            ''')
            
            # Convert to dictionary with IP as key
            clients = {}
            for row in rows:
                clients[row['ip']] = {
                    'ip': row['ip'],
                    'hostname': row['hostname'] or '',
                    'mac': row['mac'] or '',
                    'proxy': row['proxy'] or '',
                    'proxy_type': row['proxy_type'] or 'HTTP',
                    'remote_fakedns': bool(row['remote_fakedns']),
                    'created_at': row['created_at'],
                    'updated_at': row['updated_at']
                }
            
            return clients
            
        except Exception as e:
            logger.error(f"Error getting clients with proxy: {e}")
            return {}
    
    def clear_all_clients(self) -> bool:
        """Clear all client configurations (for testing/reset)"""
        try:
            # Use self.db.execute
            self.db.execute('DELETE FROM clients')
            logger.info("All client configurations cleared")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing all clients: {e}")
            return False

