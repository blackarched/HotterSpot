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
from input_validator import get_validator, ValidationError

class HotspotManager:
    def __init__(self):
        self.validator = get_validator()
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
        try:
            # Basic validation, more thorough validation should happen before calling this.
            # The input_validator's 'password' rule already checks length.
            # Here, we ensure that the validator is used for all inputs before they reach subprocess.
            validated_ssid = self.validator.validate(ssid, 'ssid', context="hotspot_mgr_create_ssid")
            validated_password = self.validator.validate(password, 'password', context="hotspot_mgr_create_password")
            validated_interface = None
            if interface:
                validated_interface = self.validator.validate(interface, 'interface', context="hotspot_mgr_create_interface")
        except ValidationError as e:
            self.logger.error(f"Hotspot configuration validation failed: {e}")
            return False
            
        if self.system == "linux":
            return self._create_linux_hotspot(validated_ssid, validated_password, validated_interface)
        elif self.system == "windows":
            # Windows hotspot creation does not typically use an interface argument in the same way with netsh for hostednetwork
            return self._create_windows_hotspot(validated_ssid, validated_password)
        else:
            self.logger.error(f"Unsupported system: {self.system}")
            return False
    
    def _create_linux_hotspot(self, ssid: str, password: str, interface: str = None) -> bool:
        """Create hotspot on Linux using nmcli"""
        try:
            # Interface validation is done in the calling public method create_hotspot
            # If interface is None here, it means it should be auto-detected or use a default.
            current_interface = interface
            if not current_interface:
                available_interfaces = self.get_available_interfaces() # This itself uses subprocess but seems safe (static command)
                if not available_interfaces:
                    self.logger.error("No available wireless interfaces for Linux hotspot.")
                    return False
                current_interface = available_interfaces[0] # Use the first available one
            
            # Re-validate if it was auto-selected, though get_available_interfaces should give valid ones.
            try:
                validated_interface_final = self.validator.validate(current_interface, 'interface', context="hotspot_mgr_linux_final_interface")
            except ValidationError as e:
                self.logger.error(f"Auto-selected interface {current_interface} is invalid: {e}")
                return False

            self.interface = validated_interface_final
            
            # Stop any existing hotspot (uses static name "HotspotTool", generally safe)
            self.stop_hotspot()
            
            # Create hotspot connection using validated inputs
            cmd = [
                "nmcli", "device", "wifi", "hotspot",
                "ifname", self.interface, # Use validated interface stored in self.interface
                "con-name", "HotspotTool", # Static name
                "ssid", ssid, # Already validated ssid
                "password", password # Already validated password
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                self.is_active = True
                self.current_ssid = ssid # Store original (or validated, they should be same format)
                self.current_password = password # Store original
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
            
            # Set up hosted network using validated inputs
            # ssid and password are pre-validated by the public create_hotspot method
            # The main risk here is if ssid or password contained characters that netsh interprets specially,
            # even if they pass basic 'ssid' and 'password' validation.
            # However, 'ssid' and 'password' rules should strip/forbid most dangerous chars.
            # For f-strings, the primary defense is ensuring the interpolated variables are clean.

            # It's safer to pass arguments individually if the tool supports it,
            # but netsh set hostednetwork often uses key=value pairs in one string.
            # We rely on the validator to have cleaned ssid and password sufficiently.

            setup_cmd_args = [
                "netsh", "wlan", "set", "hostednetwork",
                "mode=allow",
                f"ssid={ssid}", # ssid is validated
                f"key={password}"  # password is validated
            ]
            
            result_setup = subprocess.run(setup_cmd_args, capture_output=True, text=True, check=False)
            
            if result_setup.returncode != 0:
                self.logger.error(f"Failed to setup hosted network: {result_setup.stderr}")
                return False
            
            # Start hosted network (static command)
            start_cmd_args = ["netsh", "wlan", "start", "hostednetwork"]
            result_start = subprocess.run(start_cmd_args, capture_output=True, text=True, check=False)
            
            if result_start.returncode == 0:
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
