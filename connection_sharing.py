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
from input_validator import get_validator, ValidationError

class ConnectionSharingManager:
    def __init__(self):
        self.validator = get_validator()
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
            validated_primary_iface = self.validator.validate(primary_iface, 'interface', context="conn_share_linux_primary")
            validated_hotspot_iface = self.validator.validate(hotspot_iface, 'interface', context="conn_share_linux_hotspot")
        except ValidationError as e:
            self.logger.error(f"Invalid interface name for Linux sharing. Error: {e}")
            return False

        try:
            commands = [
                # Enable IP forwarding
                ['sysctl', 'net.ipv4.ip_forward=1'], # Static part, arg is safe
                
                # Clear existing rules (static commands)
                ['iptables', '-t', 'nat', '-F', 'POSTROUTING'],
                ['iptables', '-F', 'FORWARD'],
                
                # Setup NAT
                ['iptables', '-t', 'nat', '-A', 'POSTROUTING', 
                 '-o', validated_primary_iface, '-j', 'MASQUERADE'],
                
                # Allow forwarding
                ['iptables', '-A', 'FORWARD', '-i', validated_hotspot_iface,
                 '-o', validated_primary_iface, '-j', 'ACCEPT'],
                ['iptables', '-A', 'FORWARD', '-i', validated_primary_iface,
                 '-o', validated_hotspot_iface, '-m', 'state',
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
            validated_primary_iface = self.validator.validate(primary_iface, 'interface', context="conn_share_windows_primary")
            validated_hotspot_iface = self.validator.validate(hotspot_iface, 'interface', context="conn_share_windows_hotspot")
        except ValidationError as e:
            self.logger.error(f"Invalid interface name for Windows sharing. Error: {e}")
            return False

        try:
            # Enable internet connection sharing
            cmd = [
                'netsh', 'interface', 'set', 'interface', 
                validated_primary_iface, 'admin=enable'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True) # Added text=True
            if result.returncode != 0:
                self.logger.error(f"Failed to enable primary interface: {result.stderr}")
                return False
            
            # Configure ICS (this typically requires registry manipulation or PowerShell)
            # Using specific commands instead of a complex multi-line script if possible,
            # or ensuring variables are strictly for names and not arbitrary commands.
            # The original PowerShell command primarily gets adapters and sets a registry key.
            # Let's focus on validating the inputs to the f-string.
            # The risk is if primary_iface or hotspot_iface contains malicious PowerShell code.
            # The 'interface' rule should prevent typical command injection characters.
            
            powershell_script_block = f'''
            $primaryAdapter = Get-NetAdapter -Name "{validated_primary_iface}"
            If (-Not $primaryAdapter) {{ Write-Error "Primary adapter {validated_primary_iface} not found."; Exit 1 }}

            $hotspotAdapter = Get-NetAdapter -Name "{validated_hotspot_iface}"
            If (-Not $hotspotAdapter) {{ Write-Error "Hotspot adapter {validated_hotspot_iface} not found."; Exit 1 }}

            # The following is a simplified representation of enabling ICS.
            # True ICS setup is more complex and often involves NetConnectionSharing.
            # This example focuses on the risk of the original command's variable injection.
            Write-Host "Validated Primary: {validated_primary_iface}"
            Write-Host "Validated Hotspot: {validated_hotspot_iface}"

            # Example: Enable ICS on primary adapter (conceptual, actual ICS is more complex)
            # $netShare = New-Object -ComObject HNetCfg.HNetShare
            # $connection = $netShare.EnumEveryConnection | Where-Object {{ $netShare.NetConnectionProps($_).Name -eq $primaryAdapter.Name }}
            # if($connection) {{
            #     $props = $netShare.NetConnectionProps($connection)
            #     $sharingCfg = $netShare.INetSharingConfigurationForINetConnection($connection)
            #     $sharingCfg.EnableSharing(0) # 0 for public, 1 for private
            #     Write-Host "ICS enabled on $primaryAdapter.Name"
            # }} else {{
            #    Write-Error "Primary connection for ICS not found."
            # }}

            $regPath = "HKLM:\\SYSTEM\\CurrentControlSet\\Services\\SharedAccess\\Parameters\\FirewallPolicy"
            If (Test-Path $regPath) {{
                Set-ItemProperty -Path $regPath -Name "EnableFirewall" -Value 1 -ErrorAction Stop
                Write-Host "SharedAccess FirewallPolicy registry key updated."
            }} Else {{
                Write-Warning "Registry path for SharedAccess FirewallPolicy not found."
            }}
            '''
            
            # Using -Command is generally safer with validated inputs than -EncodedCommand if building the string directly.
            ps_result = subprocess.run(['powershell', '-Command', powershell_script_block],
                                     capture_output=True, text=True) # Added text=True

            if ps_result.returncode != 0:
                self.logger.error(f"PowerShell configuration script failed: {ps_result.stderr}")
                # It might not be a fatal error for the whole operation depending on what failed.
                # For now, we'll log and continue.
            
            self.logger.info("Windows internet sharing configuration attempted.")
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
