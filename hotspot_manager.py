#!/usr/bin/env python3
"""
Hotspot Manager - Core hotspot creation and management functionality
"""

import subprocess
import platform
import re
import logging
from typing import Dict, List, Optional, Tuple
import psutil
import time

class HotspotManager:
    def __init__(self):
        self.system = platform.system().lower()
        self.is_active = False
        self.current_ssid = None
        self.current_password = None
        self.interface = None
        self.logger = logging.getLogger(__name__)
        
    def get_available_interfaces(self) -> List[str]:
        """Get list of available wireless interfaces"""
        interfaces = []
        
        if self.system == "linux":
            try:
                result = subprocess.run(
                    ["nmcli", "device", "status"], 
                    capture_output=True, text=True, check=True
                )
                for line in result.stdout.split('\n'):
                    if 'wifi' in line and 'unavailable' not in line:
                        interface = line.split()[0]
                        interfaces.append(interface)
            except subprocess.CalledProcessError:
                self.logger.error("Failed to get wireless interfaces")
                
        elif self.system == "windows":
            try:
                result = subprocess.run(
                    ["netsh", "wlan", "show", "profiles"], 
                    capture_output=True, text=True, check=True
                )
                # Get default wireless adapter
                interfaces.append("wlan0")  # Default assumption
            except subprocess.CalledProcessError:
                self.logger.error("Failed to get wireless interfaces")
                
        return interfaces
    
    def create_hotspot(self, ssid: str, password: str, interface: str = None) -> bool:
        """Create and start hotspot"""
        if len(password) < 8:
            self.logger.error("Password must be at least 8 characters")
            return False
            
        if self.system == "linux":
            return self._create_linux_hotspot(ssid, password, interface)
        elif self.system == "windows":
            return self._create_windows_hotspot(ssid, password)
        else:
            self.logger.error(f"Unsupported system: {self.system}")
            return False
    
    def _create_linux_hotspot(self, ssid: str, password: str, interface: str = None) -> bool:
        """Create hotspot on Linux using nmcli"""
        try:
            if not interface:
                interfaces = self.get_available_interfaces()
                if not interfaces:
                    self.logger.error("No available wireless interfaces")
                    return False
                interface = interfaces[0]
            
            self.interface = interface
            
            # Stop any existing hotspot
            self.stop_hotspot()
            
            # Create hotspot connection
            cmd = [
                "nmcli", "device", "wifi", "hotspot",
                "ifname", interface,
                "con-name", "HotspotTool",
                "ssid", ssid,
                "password", password
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.is_active = True
                self.current_ssid = ssid
                self.current_password = password
                self.logger.info(f"Hotspot '{ssid}' created successfully")
                return True
            else:
                self.logger.error(f"Failed to create hotspot: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating Linux hotspot: {e}")
            return False
    
    def _create_windows_hotspot(self, ssid: str, password: str) -> bool:
        """Create hotspot on Windows using netsh"""
        try:
            # Stop any existing hotspot
            self.stop_hotspot()
            
            # Set up hosted network
            setup_cmd = [
                "netsh", "wlan", "set", "hostednetwork",
                "mode=allow", f"ssid={ssid}", f"key={password}"
            ]
            
            result = subprocess.run(setup_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to setup hosted network: {result.stderr}")
                return False
            
            # Start hosted network
            start_cmd = ["netsh", "wlan", "start", "hostednetwork"]
            result = subprocess.run(start_cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.is_active = True
                self.current_ssid = ssid
                self.current_password = password
                self.logger.info(f"Hotspot '{ssid}' started successfully")
                return True
            else:
                self.logger.error(f"Failed to start hotspot: {result.stderr}")
                return False
                
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error creating Windows hotspot: {e}")
            return False
    
    def stop_hotspot(self) -> bool:
        """Stop the active hotspot"""
        try:
            if self.system == "linux":
                result = subprocess.run(
                    ["nmcli", "connection", "down", "HotspotTool"],
                    capture_output=True, text=True
                )
                # Also try to delete the connection
                subprocess.run(
                    ["nmcli", "connection", "delete", "HotspotTool"],
                    capture_output=True, text=True
                )
                
            elif self.system == "windows":
                result = subprocess.run(
                    ["netsh", "wlan", "stop", "hostednetwork"],
                    capture_output=True, text=True
                )
            
            self.is_active = False
            self.current_ssid = None
            self.current_password = None
            self.logger.info("Hotspot stopped")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error stopping hotspot: {e}")
            return False
    
    def get_hotspot_status(self) -> Dict:
        """Get current hotspot status"""
        return {
            'active': self.is_active,
            'ssid': self.current_ssid,
            'password': self.current_password,
            'interface': self.interface,
            'connected_devices': len(self.get_connected_devices())
        }
    
    def get_connected_devices(self) -> List[Dict]:
        """Get list of connected devices"""
        devices = []
        
        if not self.is_active:
            return devices
            
        if self.system == "linux":
            devices = self._get_linux_connected_devices()
        elif self.system == "windows":
            devices = self._get_windows_connected_devices()
            
        return devices
    
    def _get_linux_connected_devices(self) -> List[Dict]:
        """Get connected devices on Linux"""
        devices = []
        
        try:
            # Get ARP table
            result = subprocess.run(
                ["arp", "-a"], capture_output=True, text=True
            )
            
            # Parse ARP output
            for line in result.stdout.split('\n'):
                if line.strip():
                    match = re.search(r'\(([\d.]+)\) at ([a-fA-F0-9:]+)', line)
                    if match:
                        ip = match.group(1)
                        mac = match.group(2)
                        
                        # Check if IP is in hotspot range (typically 10.42.0.x)
                        if ip.startswith('10.42.0.') or ip.startswith('192.168.'):
                            devices.append({
                                'ip': ip,
                                'mac': mac,
                                'hostname': self._get_hostname(ip),
                                'connected_time': time.time()
                            })
                            
        except subprocess.CalledProcessError:
            self.logger.error("Failed to get connected devices")
            
        return devices
    
    def _get_windows_connected_devices(self) -> List[Dict]:
        """Get connected devices on Windows"""
        devices = []
        
        try:
            # Use netsh to show clients
            result = subprocess.run(
                ["netsh", "wlan", "show", "hostednetwork"],
                capture_output=True, text=True
            )
            
            # Parse output for connected clients
            # Windows netsh output varies, so this is a basic implementation
            if "Number of clients" in result.stdout:
                for line in result.stdout.split('\n'):
                    if 'Authentication' in line and 'Yes' in line:
                        # Basic parsing - would need enhancement for real MAC addresses
                        devices.append({
                            'ip': 'Unknown',
                            'mac': 'Unknown',
                            'hostname': 'Unknown',
                            'connected_time': time.time()
                        })
                        
        except subprocess.CalledProcessError:
            self.logger.error("Failed to get connected devices")
            
        return devices
    
    def _get_hostname(self, ip: str) -> str:
        """Get hostname for IP address"""
        try:
            import socket
            hostname = socket.gethostbyaddr(ip)[0]
            return hostname
        except:
            return "Unknown"
    
    def disconnect_device(self, mac_address: str) -> bool:
        """Disconnect a specific device"""
        # This is complex and system-dependent
        # For now, return False as it requires advanced network management
        self.logger.warning("Device disconnection not implemented")
        return False
    
    def get_data_usage(self) -> Dict:
        """Get data usage statistics"""
        if not self.interface:
            return {'bytes_sent': 0, 'bytes_recv': 0}
            
        try:
            stats = psutil.net_io_counters(pernic=True)
            if self.interface in stats:
                return {
                    'bytes_sent': stats[self.interface].bytes_sent,
                    'bytes_recv': stats[self.interface].bytes_recv,
                    'packets_sent': stats[self.interface].packets_sent,
                    'packets_recv': stats[self.interface].packets_recv
                }
        except:
            pass
            
        return {'bytes_sent': 0, 'bytes_recv': 0, 'packets_sent': 0, 'packets_recv': 0}
