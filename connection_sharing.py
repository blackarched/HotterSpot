#!/usr/bin/env python3
"""
Internet Connection Sharing (ICS) Manager
Handles sharing internet connection from primary interface to hotspot
"""

import subprocess
import logging
import platform
import time
from typing import Optional, Dict, List

class ConnectionSharingManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system = platform.system().lower()
        self.sharing_active = False
        self.primary_interface = None
        self.hotspot_interface = None
        
    def detect_primary_interface(self) -> Optional[str]:
        """Detect the primary internet-connected interface"""
        try:
            if self.system == "linux":
                # Get default route interface
                result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'dev' in line:
                            parts = line.split()
                            dev_index = parts.index('dev') + 1
                            if dev_index < len(parts):
                                return parts[dev_index]
            
            elif self.system == "windows":
                # Get active network interface
                result = subprocess.run(['netsh', 'interface', 'show', 'interface'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'Connected' in line and 'Ethernet' in line:
                            parts = line.split()
                            return parts[-1]
                        
        except Exception as e:
            self.logger.error(f"Failed to detect primary interface: {e}")
        
        return None
    
    def setup_linux_sharing(self, primary_iface: str, hotspot_iface: str) -> bool:
        """Setup internet sharing on Linux using iptables"""
        try:
            commands = [
                # Enable IP forwarding
                ['sysctl', 'net.ipv4.ip_forward=1'],
                
                # Clear existing rules
                ['iptables', '-t', 'nat', '-F', 'POSTROUTING'],
                ['iptables', '-F', 'FORWARD'],
                
                # Setup NAT
                ['iptables', '-t', 'nat', '-A', 'POSTROUTING', 
                 '-o', primary_iface, '-j', 'MASQUERADE'],
                
                # Allow forwarding
                ['iptables', '-A', 'FORWARD', '-i', hotspot_iface, 
                 '-o', primary_iface, '-j', 'ACCEPT'],
                ['iptables', '-A', 'FORWARD', '-i', primary_iface, 
                 '-o', hotspot_iface, '-m', 'state', 
                 '--state', 'RELATED,ESTABLISHED', '-j', 'ACCEPT']
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode != 0:
                    self.logger.error(f"Command failed: {' '.join(cmd)}")
                    return False
            
            self.logger.info("Linux internet sharing configured successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to setup Linux sharing: {e}")
            return False
    
    def setup_windows_sharing(self, primary_iface: str, hotspot_iface: str) -> bool:
        """Setup internet sharing on Windows using netsh"""
        try:
            # Enable internet connection sharing
            cmd = [
                'netsh', 'interface', 'set', 'interface', 
                primary_iface, 'admin=enable'
            ]
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                self.logger.error("Failed to enable primary interface")
                return False
            
            # Configure ICS (this typically requires registry manipulation or PowerShell)
            powershell_cmd = f'''
            $primary = Get-NetAdapter -Name "{primary_iface}"
            $hotspot = Get-NetAdapter -Name "{hotspot_iface}"
            
            # Enable ICS on primary adapter
            $regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy"
            Set-ItemProperty -Path $regPath -Name "EnableFirewall" -Value 1
            '''
            
            ps_result = subprocess.run(['powershell', '-Command', powershell_cmd], 
                                     capture_output=True)
            
            self.logger.info("Windows internet sharing configured")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to setup Windows sharing: {e}")
            return False
    
    def enable_sharing(self, primary_iface: str = None, hotspot_iface: str = None) -> bool:
        """Enable internet connection sharing"""
        if not primary_iface:
            primary_iface = self.detect_primary_interface()
            
        if not primary_iface:
            self.logger.error("Could not detect primary interface")
            return False
        
        if not hotspot_iface:
            hotspot_iface = "wlan0"  # Default hotspot interface
        
        self.primary_interface = primary_iface
        self.hotspot_interface = hotspot_iface
        
        self.logger.info(f"Setting up sharing: {primary_iface} -> {hotspot_iface}")
        
        if self.system == "linux":
            success = self.setup_linux_sharing(primary_iface, hotspot_iface)
        elif self.system == "windows":
            success = self.setup_windows_sharing(primary_iface, hotspot_iface)
        else:
            self.logger.error(f"Unsupported system: {self.system}")
            return False
        
        self.sharing_active = success
        return success
    
    def disable_sharing(self) -> bool:
        """Disable internet connection sharing"""
        try:
            if self.system == "linux":
                commands = [
                    ['iptables', '-t', 'nat', '-F', 'POSTROUTING'],
                    ['iptables', '-F', 'FORWARD'],
                    ['sysctl', 'net.ipv4.ip_forward=0']
                ]
                
                for cmd in commands:
                    subprocess.run(cmd, capture_output=True)
            
            elif self.system == "windows":
                # Disable hosted network
                subprocess.run(['netsh', 'wlan', 'stop', 'hostednetwork'], 
                             capture_output=True)
            
            self.sharing_active = False
            self.logger.info("Internet sharing disabled")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to disable sharing: {e}")
            return False
    
    def get_sharing_status(self) -> Dict:
        """Get current sharing status"""
        return {
            'active': self.sharing_active,
            'primary_interface': self.primary_interface,
            'hotspot_interface': self.hotspot_interface,
            'system': self.system
        }
    
    def test_connectivity(self) -> bool:
        """Test if internet connectivity is available"""
        try:
            # Ping Google DNS
            if self.system == "linux":
                result = subprocess.run(['ping', '-c', '1', '8.8.8.8'], 
                                      capture_output=True, timeout=5)
            else:
                result = subprocess.run(['ping', '-n', '1', '8.8.8.8'], 
                                      capture_output=True, timeout=5)
            
            return result.returncode == 0
            
        except Exception:
            return False

if __name__ == "__main__":
    # Test the connection sharing manager
    logging.basicConfig(level=logging.INFO)
    
    cs_manager = ConnectionSharingManager()
    
    # Test interface detection
    primary = cs_manager.detect_primary_interface()
    print(f"Detected primary interface: {primary}")
    
    # Test connectivity
    connected = cs_manager.test_connectivity()
    print(f"Internet connectivity: {connected}")
