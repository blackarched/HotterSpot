#!/usr/bin/env python3
"""
User Manager - Device and user management functionality
"""

import subprocess
import platform
import logging
import json
import sqlite3
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import threading
from input_validator import get_validator, ValidationError

class UserManager:
    def __init__(self, db_path: str = "users.db"):
        self.validator = get_validator()
        self.system = platform.system().lower()
        self.logger = logging.getLogger(__name__)
        self.db_path = db_path
        self.blocked_devices = set()
        self.device_data_usage = {}
        self.monitoring_active = False
        self.monitor_thread = None
        
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for user management"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    mac_address TEXT PRIMARY KEY,
                    hostname TEXT,
                    first_seen TIMESTAMP,
                    last_seen TIMESTAMP,
                    is_blocked BOOLEAN DEFAULT 0,
                    total_bytes_sent INTEGER DEFAULT 0,
                    total_bytes_recv INTEGER DEFAULT 0,
                    friendly_name TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS data_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mac_address TEXT,
                    timestamp TIMESTAMP,
                    bytes_sent INTEGER,
                    bytes_recv INTEGER,
                    FOREIGN KEY (mac_address) REFERENCES devices (mac_address)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blocked_devices (
                    mac_address TEXT PRIMARY KEY,
                    blocked_at TIMESTAMP,
                    reason TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database: {e}")
    
    def register_device(self, device_info: Dict) -> bool:
        """Register a new device or update existing device info"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            mac = device_info.get('mac', '').upper()
            hostname = device_info.get('hostname', 'Unknown')
            friendly_name = device_info.get('friendly_name', hostname)
            
            # Check if device exists
            cursor.execute('SELECT mac_address FROM devices WHERE mac_address = ?', (mac,))
            exists = cursor.fetchone()
            
            if exists:
                # Update last seen
                cursor.execute('''
                    UPDATE devices 
                    SET last_seen = ?, hostname = ?, friendly_name = ?
                    WHERE mac_address = ?
                ''', (datetime.now(), hostname, friendly_name, mac))
            else:
                # Insert new device
                cursor.execute('''
                    INSERT INTO devices 
                    (mac_address, hostname, first_seen, last_seen, friendly_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (mac, hostname, datetime.now(), datetime.now(), friendly_name))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register device: {e}")
            return False
    
    def get_all_devices(self) -> List[Dict]:
        """Get all registered devices"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT mac_address, hostname, first_seen, last_seen, 
                       is_blocked, total_bytes_sent, total_bytes_recv, friendly_name
                FROM devices
                ORDER BY last_seen DESC
            ''')
            
            devices = []
            for row in cursor.fetchall():
                devices.append({
                    'mac': row[0],
                    'hostname': row[1],
                    'first_seen': row[2],
                    'last_seen': row[3],
                    'is_blocked': bool(row[4]),
                    'total_bytes_sent': row[5],
                    'total_bytes_recv': row[6],
                    'friendly_name': row[7]
                })
            
            conn.close()
            return devices
            
        except Exception as e:
            self.logger.error(f"Failed to get devices: {e}")
            return []
    
    def block_device(self, mac_address: str, reason: str = "Manual block") -> bool:
        """Block a device from accessing the network"""
        try:
            mac = mac_address.upper()
            
            # Add to database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO blocked_devices 
                (mac_address, blocked_at, reason)
                VALUES (?, ?, ?)
            ''', (mac, datetime.now(), reason))
            
            cursor.execute('''
                UPDATE devices SET is_blocked = 1 WHERE mac_address = ?
            ''', (mac,))
            
            conn.commit()
            conn.close()
            
            # Add to memory set
            self.blocked_devices.add(mac)
            
            # Apply network-level blocking
            if self.system == "linux":
                self._block_device_linux(mac)
            elif self.system == "windows":
                self._block_device_windows(mac)
            
            self.logger.info(f"Device {mac} blocked: {reason}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to block device: {e}")
            return False
    
    def unblock_device(self, mac_address: str) -> bool:
        """Unblock a device"""
        try:
            mac = mac_address.upper()
            
            # Remove from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM blocked_devices WHERE mac_address = ?', (mac,))
            cursor.execute('UPDATE devices SET is_blocked = 0 WHERE mac_address = ?', (mac,))
            
            conn.commit()
            conn.close()
            
            # Remove from memory set
            self.blocked_devices.discard(mac)
            
            # Remove network-level blocking
            if self.system == "linux":
                self._unblock_device_linux(mac)
            elif self.system == "windows":
                self._unblock_device_windows(mac)
            
            self.logger.info(f"Device {mac} unblocked")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to unblock device: {e}")
            return False
    
    def _block_device_linux(self, mac_address: str):
        """Block device on Linux using iptables"""
        # This is an internal method; mac_address should be validated by public calling methods.
        # However, adding validation here for defense in depth.
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="user_mgr_block_linux_mac")
        except ValidationError as e:
            self.logger.error(f"Invalid MAC address for _block_device_linux: {mac_address}. Error: {e}")
            return

        try:
            # Block by MAC address
            subprocess.run([
                "iptables", "-I", "FORWARD", "-m", "mac", 
                "--mac-source", validated_mac, "-j", "DROP"
            ], check=True) # check=True will raise CalledProcessError on failure
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to block device {validated_mac} with iptables: {e.stderr}")
        except FileNotFoundError:
            self.logger.error(f"iptables command not found when trying to block {validated_mac}.")
    
    def _unblock_device_linux(self, mac_address: str):
        """Unblock device on Linux using iptables"""
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="user_mgr_unblock_linux_mac")
        except ValidationError as e:
            self.logger.error(f"Invalid MAC address for _unblock_device_linux: {mac_address}. Error: {e}")
            return

        try:
            # Remove block rule
            # Using check=False as the rule might not exist, and that's fine for an unblock operation.
            subprocess.run([
                "iptables", "-D", "FORWARD", "-m", "mac", 
                "--mac-source", validated_mac, "-j", "DROP"
            ], check=False, capture_output=True, text=True)
            
        except FileNotFoundError:
             self.logger.error(f"iptables command not found when trying to unblock {validated_mac}.")
        except Exception as e: # Catch any other potential errors
            self.logger.error(f"An unexpected error occurred while trying to unblock {validated_mac}: {e}")

    
    def _block_device_windows(self, mac_address: str):
        """Block device on Windows (limited functionality)"""
        # Windows has limited MAC-based blocking capabilities
        self.logger.warning("Windows MAC-based blocking has limited functionality")
    
    def _unblock_device_windows(self, mac_address: str):
        """Unblock device on Windows"""
        self.logger.warning("Windows MAC-based unblocking has limited functionality")
    
    def get_blocked_devices(self) -> List[Dict]:
        """Get list of blocked devices"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT bd.mac_address, bd.blocked_at, bd.reason, d.hostname, d.friendly_name
                FROM blocked_devices bd
                LEFT JOIN devices d ON bd.mac_address = d.mac_address
            ''')
            
            blocked = []
            for row in cursor.fetchall():
                blocked.append({
                    'mac': row[0],
                    'blocked_at': row[1],
                    'reason': row[2],
                    'hostname': row[3] or 'Unknown',
                    'friendly_name': row[4] or row[3] or 'Unknown'
                })
            
            conn.close()
            return blocked
            
        except Exception as e:
            self.logger.error(f"Failed to get blocked devices: {e}")
            return []
    
    def record_data_usage(self, mac_address: str, bytes_sent: int, bytes_recv: int):
        """Record data usage for a device"""
        try:
            mac = mac_address.upper()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Record usage snapshot
            cursor.execute('''
                INSERT INTO data_usage (mac_address, timestamp, bytes_sent, bytes_recv)
                VALUES (?, ?, ?, ?)
            ''', (mac, datetime.now(), bytes_sent, bytes_recv))
            
            # Update total usage
            cursor.execute('''
                UPDATE devices 
                SET total_bytes_sent = total_bytes_sent + ?,
                    total_bytes_recv = total_bytes_recv + ?
                WHERE mac_address = ?
            ''', (bytes_sent, bytes_recv, mac))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            self.logger.error(f"Failed to record data usage: {e}")
    
    def get_device_usage(self, mac_address: str, hours: int = 24) -> Dict:
        """Get data usage for a device over specified time period"""
        try:
            mac = mac_address.upper()
            since = datetime.now() - timedelta(hours=hours)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT SUM(bytes_sent), SUM(bytes_recv), COUNT(*)
                FROM data_usage
                WHERE mac_address = ? AND timestamp >= ?
            ''', (mac, since))
            
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0] is not None:
                return {
                    'bytes_sent': result[0],
                    'bytes_recv': result[1],
                    'total_bytes': result[0] + result[1],
                    'samples': result[2],
                    'period_hours': hours
                }
            
            return {'bytes_sent': 0, 'bytes_recv': 0, 'total_bytes': 0, 'samples': 0}
            
        except Exception as e:
            self.logger.error(f"Failed to get device usage: {e}")
            return {}
    
    def set_friendly_name(self, mac_address: str, friendly_name: str) -> bool:
        """Set a friendly name for a device"""
        try:
            mac = mac_address.upper()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE devices SET friendly_name = ? WHERE mac_address = ?
            ''', (friendly_name, mac))
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Friendly name set for {mac}: {friendly_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set friendly name: {e}")
            return False
    
    def start_monitoring(self, interval: int = 60):
        """Start monitoring connected devices"""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_devices, args=(interval,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        self.logger.info("Device monitoring started")
    
    def stop_monitoring(self):
        """Stop monitoring devices"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.logger.info("Device monitoring stopped")
    
    def _monitor_devices(self, interval: int):
        """Monitor devices continuously"""
        while self.monitoring_active:
            try:
                # This would integrate with the hotspot manager to get current devices
                # For now, it's a placeholder
                time.sleep(interval)
                
            except Exception as e:
                self.logger.error(f"Error in device monitoring: {e}")
                time.sleep(interval)
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old data usage records"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM data_usage WHERE timestamp < ?', (cutoff,))
            deleted = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            self.logger.info(f"Cleaned up {deleted} old data usage records")
            return deleted
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
            return 0
    
    def get_usage_statistics(self) -> Dict:
        """Get overall usage statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Total devices
            cursor.execute('SELECT COUNT(*) FROM devices')
            total_devices = cursor.fetchone()[0]
            
            # Active devices (seen in last 24 hours)
            since = datetime.now() - timedelta(hours=24)
            cursor.execute('SELECT COUNT(*) FROM devices WHERE last_seen >= ?', (since,))
            active_devices = cursor.fetchone()[0]
            
            # Blocked devices
            cursor.execute('SELECT COUNT(*) FROM blocked_devices')
            blocked_devices = cursor.fetchone()[0]
            
            # Total data usage
            cursor.execute('SELECT SUM(total_bytes_sent), SUM(total_bytes_recv) FROM devices')
            usage = cursor.fetchone()
            total_sent = usage[0] or 0
            total_recv = usage[1] or 0
            
            conn.close()
            
            return {
                'total_devices': total_devices,
                'active_devices': active_devices,
                'blocked_devices': blocked_devices,
                'total_bytes_sent': total_sent,
                'total_bytes_recv': total_recv,
                'total_bytes': total_sent + total_recv
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get usage statistics: {e}")
            return {}