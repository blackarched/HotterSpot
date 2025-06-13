#!/usr/bin/env python3
"""
Configuration Validator
Validates hotspot configuration settings and system requirements
"""

import re
import subprocess
import platform
import logging
from typing import Dict, List, Optional, Tuple
from ipaddress import IPv4Network, AddressValueError

class ConfigValidator:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system = platform.system().lower()
        
    def validate_ssid(self, ssid: str) -> Dict[str, any]:
        """Validate SSID format and requirements"""
        validation = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Length check
        if len(ssid) < 1 or len(ssid) > 32:
            validation['valid'] = False
            validation['errors'].append("SSID must be 1-32 characters long")
        
        # Character validation
        if not re.match(r'^[a-zA-Z0-9\-_\s]+$', ssid):
            validation['valid'] = False
            validation['errors'].append("SSID contains invalid characters")
        
        # Common SSID warnings
        if ssid.lower() in ['default', 'linksys', 'netgear', 'dlink']:
            validation['warnings'].append("Using default SSID names is not recommended")
        
        if ssid.startswith(' ') or ssid.endswith(' '):
            validation['valid'] = False
            validation['errors'].append("SSID cannot start or end with spaces")
            
        return validation
    
    def validate_ip_range(self, ip_range: str) -> Dict[str, any]:
        """Validate IP address range for DHCP"""
        validation = {
            'valid': True,
            'errors': [],
            'network': None
        }
        
        try:
            network = IPv4Network(ip_range, strict=False)
            validation['network'] = network
            
            # Check for private IP ranges
            if not network.is_private:
                validation['errors'].append("IP range should be private (RFC 1918)")
                validation['valid'] = False
            
            # Check minimum host count
            if network.num_addresses < 4:
                validation['errors'].append("Network too small (minimum 4 addresses)")
                validation['valid'] = False
                
        except (AddressValueError, ValueError) as e:
            validation['valid'] = False
            validation['errors'].append(f"Invalid IP range format: {e}")
            
        return validation
    
    def validate_channel(self, channel: int, band: str = "2.4GHz") -> Dict[str, any]:
        """Validate Wi-Fi channel selection"""
        validation = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        if band == "2.4GHz":
            valid_channels = list(range(1, 15))  # Channels 1-14
            if channel not in valid_channels:
                validation['valid'] = False
                validation['errors'].append(f"Invalid 2.4GHz channel: {channel}")
            
            # Recommend non-overlapping channels
            if channel not in [1, 6, 11]:
                validation['warnings'].append("Channels 1, 6, 11 are recommended for 2.4GHz")
                
        elif band == "5GHz":
            # Common 5GHz channels (varies by region)
            valid_channels = [36, 40, 44, 48, 149, 153, 157, 161, 165]
            if channel not in valid_channels:
                validation['valid'] = False
                validation['errors'].append(f"Invalid 5GHz channel: {channel}")
                
        return validation
    
    def validate_port(self, port: int, service: str = "generic") -> Dict[str, any]:
        """Validate port number and check for conflicts"""
        validation = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Basic port range check
        if port < 1 or port > 65535:
            validation['valid'] = False
            validation['errors'].append("Port must be between 1-65535")
            return validation
        
        # Check privileged ports
        if port < 1024:
            validation['warnings'].append("Using privileged port (requires root)")
        
        # Check common service ports
        common_ports = {
            80: "HTTP", 443: "HTTPS", 22: "SSH", 21: "FTP",
            25: "SMTP", 53: "DNS", 67: "DHCP", 68: "DHCP"
        }
        
        if port in common_ports and service.lower() != common_ports[port].lower():
            validation['warnings'].append(f"Port {port} commonly used for {common_ports[port]}")
        
        # Check if port is in use
        if self._is_port_in_use(port):
            validation['valid'] = False
            validation['errors'].append(f"Port {port} is already in use")
            
        return validation
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use"""
        try:
            if self.system == "linux":
                result = subprocess.run(['netstat', '-ln'], capture_output=True, text=True)
                return f":{port} " in result.stdout
            elif self.system == "windows":
                result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
                return f":{port} " in result.stdout
        except Exception:
            return False
    
    def _check_required_tools(self) -> Dict[str, bool]:
        """Check availability of required system tools"""
        tools = {}
        
        if self.system == "linux":
            required_tools = ['nmcli', 'iptables', 'hostapd', 'dnsmasq', 'iw']
        elif self.system == "windows":
            required_tools = ['netsh', 'powershell']
        else:
            required_tools = []
        
        for tool in required_tools:
            try:
                result = subprocess.run([tool, '--help'], 
                                      capture_output=True, timeout=5)
                tools[tool] = result.returncode in [0, 1]  # Some tools return 1 for help
            except (subprocess.TimeoutExpired, FileNotFoundError):
                tools[tool] = False
        
        return tools
    
    def _check_security_support(self) -> List[str]:
        """Check supported security protocols"""
        supported = []
        
        try:
            if self.system == "linux":
                # Check hostapd capabilities
                result = subprocess.run(['hostapd', '-v'], capture_output=True, text=True)
                stderr = result.stderr.lower()
                
                if 'wpa' in stderr:
                    supported.append('WPA2-PSK')
                if 'sae' in stderr or 'wpa3' in stderr:
                    supported.append('WPA3-SAE')
                
                # Check driver capabilities
                result = subprocess.run(['iw', 'list'], capture_output=True, text=True)
                if 'sae' in result.stdout.lower():
                    if 'WPA3-SAE' not in supported:
                        supported.append('WPA3-SAE')
                        
            elif self.system == "windows":
                # Windows typically supports WPA2
                supported.append('WPA2-PSK')
                
                # Check for WPA3 support (Windows 10 1903+)
                result = subprocess.run(['netsh', 'wlan', 'show', 'drivers'], 
                                      capture_output=True, text=True)
                if 'wpa3' in result.stdout.lower():
                    supported.append('WPA3-SAE')
        
        except Exception as e:
            self.logger.error(f"Failed to check security support: {e}")
        
        return supported
    
    def validate_bandwidth_limit(self, limit_mbps: float) -> Dict[str, any]:
        """Validate bandwidth limit settings"""
        validation = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        if limit_mbps <= 0:
            validation['valid'] = False
            validation['errors'].append("Bandwidth limit must be positive")
        
        if limit_mbps < 0.1:
            validation['warnings'].append("Very low bandwidth limit may cause connectivity issues")
        
        if limit_mbps > 1000:
            validation['warnings'].append("Very high bandwidth limit may not be enforceable")
        
        return validation
    
    def validate_dns_servers(self, dns_servers: List[str]) -> Dict[str, any]:
        """Validate DNS server addresses"""
        validation = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'valid_servers': []
        }
        
        if not dns_servers:
            validation['errors'].append("At least one DNS server required")
            validation['valid'] = False
            return validation
        
        for dns in dns_servers:
            try:
                from ipaddress import ip_address
                ip = ip_address(dns)
                validation['valid_servers'].append(str(ip))
                
                # Check for common DNS servers
                if str(ip) in ['8.8.8.8', '1.1.1.1', '208.67.222.222']:
                    validation['warnings'].append(f"Using public DNS: {ip}")
                    
            except ValueError:
                validation['valid'] = False
                validation['errors'].append(f"Invalid DNS server address: {dns}")
        
        return validation
    
    def validate_complete_config(self, config: Dict) -> Dict[str, any]:
        """Validate complete hotspot configuration"""
        validation = {
            'valid': True,
            'errors': [],
            'warnings': []
        }
        
        # Validate SSID
        if 'ssid' in config:
            ssid_val = self.validate_ssid(config['ssid'])
            if not ssid_val['valid']:
                validation['valid'] = False
                validation['errors'].extend(ssid_val['errors'])
            validation['warnings'].extend(ssid_val['warnings'])
        
        # Validate IP range
        if 'ip_range' in config:
            ip_val = self.validate_ip_range(config['ip_range'])
            if not ip_val['valid']:
                validation['valid'] = False
                validation['errors'].extend(ip_val['errors'])
        
        # Validate channel
        if 'channel' in config:
            channel_val = self.validate_channel(config['channel'], 
                                               config.get('band', '2.4GHz'))
            if not channel_val['valid']:
                validation['valid'] = False
                validation['errors'].extend(channel_val['errors'])
            validation['warnings'].extend(channel_val['warnings'])
        
        # Validate ports
        port_services = [
            ('dhcp_port', 'dhcp'),
            ('dns_port', 'dns'),
            ('captive_portal_port', 'http')
        ]
        
        for port_key, service in port_services:
            if port_key in config:
                port_val = self.validate_port(config[port_key], service)
                if not port_val['valid']:
                    validation['valid'] = False
                    validation['errors'].extend(port_val['errors'])
                validation['warnings'].extend(port_val['warnings'])
        
        # Validate bandwidth limits
        if 'bandwidth_limit' in config:
            bw_val = self.validate_bandwidth_limit(config['bandwidth_limit'])
            if not bw_val['valid']:
                validation['valid'] = False
                validation['errors'].extend(bw_val['errors'])
            validation['warnings'].extend(bw_val['warnings'])
        
        # Validate DNS servers
        if 'dns_servers' in config:
            dns_val = self.validate_dns_servers(config['dns_servers'])
            if not dns_val['valid']:
                validation['valid'] = False
                validation['errors'].extend(dns_val['errors'])
            validation['warnings'].extend(dns_val['warnings'])
        
        return validation
    
    def get_recommended_config(self) -> Dict:
        """Get recommended configuration based on system capabilities"""
        wifi_interfaces = self._get_wifi_interfaces()
        
        config = {
            'ssid': 'MyHotspot',
            'security': 'WPA2-PSK',
            'channel': 6,
            'band': '2.4GHz',
            'ip_range': '192.168.4.0/24',
            'dhcp_start': '192.168.4.100',
            'dhcp_end': '192.168.4.200',
            'dns_servers': ['8.8.8.8', '8.8.4.4'],
            'bandwidth_limit': 10.0,  # 10 Mbps
            'max_clients': 10,
            'interface': wifi_interfaces[0] if wifi_interfaces else 'wlan0'
        }
        
        # Adjust for system capabilities
        supported_security = self._check_security_support()
        if 'WPA3-SAE' in supported_security:
            config['security'] = 'WPA3-SAE'
        
        return config

if __name__ == "__main__":
    # Test the configuration validator
    logging.basicConfig(level=logging.INFO)
    
    validator = ConfigValidator()
    
    # Test system requirements
    print("System Requirements Check:")
    requirements = validator.check_system_requirements()
    print(f"Wi-Fi Capable: {requirements['wifi_capable']}")
    print(f"Wi-Fi Interfaces: {requirements['wifi_interfaces']}")
    print(f"Root Access: {requirements['root_access']}")
    print(f"Required Tools: {requirements['required_tools']}")
    print(f"Supported Security: {requirements['supported_security']}")
    
    if requirements['errors']:
        print("Errors:", requirements['errors'])
    if requirements['warnings']:
        print("Warnings:", requirements['warnings'])
    
    # Test configuration validation
    print("\nConfiguration Validation:")
    test_config = {
        'ssid': 'TestHotspot',
        'ip_range': '192.168.4.0/24',
        'channel': 6,
        'dns_servers': ['8.8.8.8', '1.1.1.1'],
        'bandwidth_limit': 5.0
    }
    
    validation = validator.validate_complete_config(test_config)
    print(f"Configuration Valid: {validation['valid']}")
    if validation['errors']:
        print("Errors:", validation['errors'])
    if validation['warnings']:
        print("Warnings:", validation['warnings'])
    
    # Get recommended configuration
    print("\nRecommended Configuration:")
    recommended = validator.get_recommended_config()
    for key, value in recommended.items():
        print(f"{key}: {value}")
        
        return False
    
    def check_system_requirements(self) -> Dict[str, any]:
        """Check if system meets hotspot requirements"""
        requirements = {
            'wifi_capable': False,
            'wifi_interfaces': [],
            'root_access': False,
            'required_tools': {},
            'supported_security': [],
            'errors': [],
            'warnings': []
        }
        
        # Check Wi-Fi interfaces
        wifi_interfaces = self._get_wifi_interfaces()
        requirements['wifi_interfaces'] = wifi_interfaces
        requirements['wifi_capable'] = len(wifi_interfaces) > 0
        
        if not requirements['wifi_capable']:
            requirements['errors'].append("No Wi-Fi interfaces detected")
        
        # Check root/admin access
        requirements['root_access'] = self._check_root_access()
        if not requirements['root_access']:
            requirements['errors'].append("Root/Administrator access required")
        
        # Check required tools
        tools = self._check_required_tools()
        requirements['required_tools'] = tools
        
        missing_tools = [tool for tool, available in tools.items() if not available]
        if missing_tools:
            requirements['errors'].extend([f"Missing tool: {tool}" for tool in missing_tools])
        
        # Check security capabilities
        requirements['supported_security'] = self._check_security_support()
        
        return requirements
    
    def _get_wifi_interfaces(self) -> List[str]:
        """Get available Wi-Fi interfaces"""
        interfaces = []
        
        try:
            if self.system == "linux":
                result = subprocess.run(['iw', 'dev'], capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Interface' in line:
                            interface = line.split()[-1]
                            interfaces.append(interface)
            
            elif self.system == "windows":
                result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Name' in line and 'Wi-Fi' in line:
                            interface = line.split(':')[-1].strip()
                            interfaces.append(interface)
                            
        except Exception as e:
            self.logger.error(f"Failed to get Wi-Fi interfaces: {e}")
            
        return interfaces
    
    def _check_root_access(self) -> bool:
        """Check if running with root/admin privileges"""
        try:
            if self.system == "linux":
                import os
                return os.geteuid() == 0
            elif self.system == "windows":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
        