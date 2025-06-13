#!/usr/bin/env python3
"""
Security Manager for Hotspot
Handles WPA2/WPA3 security, encryption, and access control
"""

import subprocess
import logging
import hashlib
import secrets
import re
from typing import Dict, List, Optional
from enum import Enum

class SecurityProtocol(Enum):
    OPEN = "open"
    WPA2_PSK = "wpa2-psk"
    WPA3_SAE = "wpa3-sae"
    WPA_MIXED = "wpa-mixed"

class SecurityManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.blocked_devices = set()
        self.allowed_devices = set()
        self.whitelist_mode = False
        
    def validate_password(self, password: str) -> Dict[str, bool]:
        """Validate password strength"""
        validation = {
            'length_ok': len(password) >= 8,
            'has_upper': bool(re.search(r'[A-Z]', password)),
            'has_lower': bool(re.search(r'[a-z]', password)),
            'has_digit': bool(re.search(r'\d', password)),
            'has_special': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
            'no_common_words': not self._contains_common_words(password),
            'valid': False
        }
        
        # Determine overall validity
        basic_requirements = validation['length_ok']
        strength_score = sum([
            validation['has_upper'],
            validation['has_lower'], 
            validation['has_digit'],
            validation['has_special']
        ])
        
        validation['valid'] = basic_requirements and strength_score >= 2
        return validation
    
    def _contains_common_words(self, password: str) -> bool:
        """Check if password contains common weak words"""
        common_words = {
            'password', '123456', 'admin', 'wifi', 'hotspot',
            'internet', 'guest', 'welcome', 'default'
        }
        password_lower = password.lower()
        return any(word in password_lower for word in common_words)
    
    def generate_secure_password(self, length: int = 12) -> str:
        """Generate a cryptographically secure password"""
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        # Ensure password meets requirements
        while not self.validate_password(password)['valid']:
            password = ''.join(secrets.choice(alphabet) for _ in range(length))
        
        return password
    
    def configure_security(self, ssid: str, password: str, 
                          protocol: SecurityProtocol = SecurityProtocol.WPA2_PSK,
                          interface: str = "wlan0") -> bool:
        """Configure security settings for the hotspot"""
        try:
            # Validate password
            if protocol != SecurityProtocol.OPEN:
                validation = self.validate_password(password)
                if not validation['valid']:
                    self.logger.error("Password does not meet security requirements")
                    return False
            
            # Configure based on protocol
            if protocol == SecurityProtocol.WPA2_PSK:
                return self._configure_wpa2(ssid, password, interface)
            elif protocol == SecurityProtocol.WPA3_SAE:
                return self._configure_wpa3(ssid, password, interface)
            elif protocol == SecurityProtocol.WPA_MIXED:
                return self._configure_mixed_wpa(ssid, password, interface)
            elif protocol == SecurityProtocol.OPEN:
                return self._configure_open(ssid, interface)
            
        except Exception as e:
            self.logger.error(f"Failed to configure security: {e}")
            return False
    
    def _configure_wpa2(self, ssid: str, password: str, interface: str) -> bool:
        """Configure WPA2-PSK security"""
        try:
            cmd = [
                'nmcli', 'device', 'wifi', 'hotspot',
                'ifname', interface,
                'con-name', f'hotspot-{ssid}',
                'ssid', ssid,
                'password', password
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info(f"WPA2 hotspot '{ssid}' configured successfully")
                return True
            else:
                self.logger.error(f"WPA2 configuration failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"WPA2 configuration error: {e}")
            return False
    
    def _configure_wpa3(self, ssid: str, password: str, interface: str) -> bool:
        """Configure WPA3-SAE security (if supported)"""
        try:
            # Check if WPA3 is supported
            if not self._check_wpa3_support():
                self.logger.warning("WPA3 not supported, falling back to WPA2")
                return self._configure_wpa2(ssid, password, interface)
            
            # Create hostapd configuration for WPA3
            config_content = f"""
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel=7
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=SAE
wpa_pairwise=CCMP
rsn_pairwise=CCMP
sae_require_mfp=1
"""
            
            # Write hostapd config
            with open('/tmp/hostapd_wpa3.conf', 'w') as f:
                f.write(config_content)
            
            # Start hostapd with WPA3 config
            cmd = ['hostapd', '/tmp/hostapd_wpa3.conf', '-B']
            result = subprocess.run(cmd, capture_output=True)
            
            if result.returncode == 0:
                self.logger.info(f"WPA3 hotspot '{ssid}' configured successfully")
                return True
            else:
                self.logger.error("WPA3 configuration failed, trying WPA2")
                return self._configure_wpa2(ssid, password, interface)
                
        except Exception as e:
            self.logger.error(f"WPA3 configuration error: {e}")
            return False
    
    def _configure_mixed_wpa(self, ssid: str, password: str, interface: str) -> bool:
        """Configure mixed WPA2/WPA3 security"""
        config_content = f"""
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel=7
wmm_enabled=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK SAE
wpa_pairwise=TKIP CCMP
rsn_pairwise=CCMP
"""
        
        try:
            with open('/tmp/hostapd_mixed.conf', 'w') as f:
                f.write(config_content)
            
            cmd = ['hostapd', '/tmp/hostapd_mixed.conf', '-B']
            result = subprocess.run(cmd, capture_output=True)
            
            return result.returncode == 0
            
        except Exception as e:
            self.logger.error(f"Mixed WPA configuration error: {e}")
            return False
    
    def _configure_open(self, ssid: str, interface: str) -> bool:
        """Configure open (no security) hotspot"""
        try:
            cmd = [
                'nmcli', 'device', 'wifi', 'hotspot',
                'ifname', interface,
                'con-name', f'hotspot-{ssid}',
                'ssid', ssid
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            self.logger.error(f"Open hotspot configuration error: {e}")
            return False
    
    def _check_wpa3_support(self) -> bool:
        """Check if the system supports WPA3"""
        try:
            # Check hostapd version and capabilities
            result = subprocess.run(['hostapd', '-v'], capture_output=True, text=True)
            if 'SAE' in result.stderr or 'WPA3' in result.stderr:
                return True
            
            # Check driver capabilities
            result = subprocess.run(['iw', 'list'], capture_output=True, text=True)
            if 'SAE' in result.stdout:
                return True
                
            return False
            
        except Exception:
            return False
    
    def block_device(self, mac_address: str) -> bool:
        """Block a device by MAC address"""
        try:
            mac_address = mac_address.upper()
            self.blocked_devices.add(mac_address)
            
            # Add iptables rule to block the MAC
            cmd = [
                'iptables', '-A', 'FORWARD',
                '-m', 'mac', '--mac-source', mac_address,
                '-j', 'DROP'
            ]
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                self.logger.info(f"Blocked device: {mac_address}")
                return True
            else:
                self.blocked_devices.discard(mac_address)
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to block device {mac_address}: {e}")
            return False
    
    def unblock_device(self, mac_address: str) -> bool:
        """Unblock a device by MAC address"""
        try:
            mac_address = mac_address.upper()
            self.blocked_devices.discard(mac_address)
            
            # Remove iptables rule
            cmd = [
                'iptables', '-D', 'FORWARD',
                '-m', 'mac', '--mac-source', mac_address,
                '-j', 'DROP'
            ]
            
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode == 0:
                self.logger.info(f"Unblocked device: {mac_address}")
                return True
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to unblock device {mac_address}: {e}")
            return False
    
    def enable_whitelist_mode(self, allowed_macs: List[str]) -> bool:
        """Enable whitelist mode - only allow specified MAC addresses"""
        try:
            self.allowed_devices = set(mac.upper() for mac in allowed_macs)
            self.whitelist_mode = True
            
            # Block all devices first
            subprocess.run(['iptables', '-A', 'FORWARD', '-j', 'DROP'], 
                         capture_output=True)
            
            # Allow specific MACs
            for mac in self.allowed_devices:
                cmd = [
                    'iptables', '-I', 'FORWARD',
                    '-m', 'mac', '--mac-source', mac,
                    '-j', 'ACCEPT'
                ]
                subprocess.run(cmd, capture_output=True)
            
            self.logger.info(f"Whitelist mode enabled for {len(allowed_macs)} devices")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to enable whitelist mode: {e}")
            return False
    
    def disable_whitelist_mode(self) -> bool:
        """Disable whitelist mode"""
        try:
            self.whitelist_mode = False
            self.allowed_devices.clear()
            
            # Flush FORWARD chain
            subprocess.run(['iptables', '-F', 'FORWARD'], capture_output=True)
            
            self.logger.info("Whitelist mode disabled")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to disable whitelist mode: {e}")
            return False
    
    def get_security_status(self) -> Dict:
        """Get current security configuration status"""
        return {
            'blocked_devices': list(self.blocked_devices),
            'allowed_devices': list(self.allowed_devices),
            'whitelist_mode': self.whitelist_mode,
            'wpa3_supported': self._check_wpa3_support()
        }

if __name__ == "__main__":
    # Test the security manager
    logging.basicConfig(level=logging.INFO)
    
    sec_manager = SecurityManager()
    
    # Test password validation
    test_passwords = ['weak', 'StrongPass123!', '12345678']
    for pwd in test_passwords:
        result = sec_manager.validate_password(pwd)
        print(f"Password '{pwd}': {result['valid']}")
    
    # Generate secure password
    secure_pwd = sec_manager.generate_secure_password()
    print(f"Generated secure password: {secure_pwd}")
