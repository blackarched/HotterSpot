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
from input_validator import get_validator, ValidationError

class SecurityProtocol(Enum):
    OPEN = "open"
    WPA2_PSK = "wpa2-psk"
    WPA3_SAE = "wpa3-sae"
    WPA_MIXED = "wpa-mixed"

class SecurityManager:
    def __init__(self):
        self.validator = get_validator()
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
            validated_ssid = self.validator.validate(ssid, 'ssid', context="sec_mgr_config_ssid")
            validated_interface = self.validator.validate(interface, 'interface', context="sec_mgr_config_interface")
            validated_password = None

            if protocol != SecurityProtocol.OPEN:
                # The 'password' rule also checks length and common weak passwords.
                # self.validate_password() is a local strength checker, could be redundant if validator's 'password' rule is robust.
                # For consistency, we'll use validator's 'password' rule.
                validated_password = self.validator.validate(password, 'password', context="sec_mgr_config_password")
                # local_validation = self.validate_password(password) # Keep this if it adds more checks not in validator
                # if not local_validation['valid']:
                #     self.logger.error("Password does not meet local security requirements (strength).")
                #     return False
            
            # Configure based on protocol
            if protocol == SecurityProtocol.WPA2_PSK:
                return self._configure_wpa2(validated_ssid, validated_password, validated_interface)
            elif protocol == SecurityProtocol.WPA3_SAE:
                return self._configure_wpa3(validated_ssid, validated_password, validated_interface)
            elif protocol == SecurityProtocol.WPA_MIXED:
                return self._configure_mixed_wpa(validated_ssid, validated_password, validated_interface)
            elif protocol == SecurityProtocol.OPEN:
                return self._configure_open(validated_ssid, validated_interface) # No password for OPEN
            
        except ValidationError as ve:
            self.logger.error(f"Input validation failed for security configuration: {ve}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to configure security: {e}")
            return False
    
    def _configure_wpa2(self, ssid: str, password: str, interface: str) -> bool:
        """Configure WPA2-PSK security"""
        # Inputs (ssid, password, interface) are assumed to be pre-validated by the calling method.
        try:
            # Ensure con-name is also safe. Using a sanitized version of SSID for it.
            safe_con_name_suffix = self.validator.validate(ssid, 'filename', context="sec_mgr_wpa2_conname_suffix")
            con_name = f'hotspot-{safe_con_name_suffix}'

            cmd = [
                'nmcli', 'device', 'wifi', 'hotspot',
                'ifname', interface, # validated interface
                'con-name', con_name,
                'ssid', ssid,       # validated ssid
                'password', password # validated password
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
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
            # Check if WPA3 is supported (uses static commands, safe)
            if not self._check_wpa3_support():
                self.logger.warning("WPA3 not supported, falling back to WPA2")
                return self._configure_wpa2(ssid, password, interface) # Already validated inputs
            
            # Create hostapd configuration for WPA3
            # Inputs (ssid, password, interface) are assumed to be pre-validated.
            # Ensure no injection into config_content. 'interface', 'ssid', 'password' rules should prevent this.
            config_content = f"""interface={interface}
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
            # Using a temporary file for hostapd config is common. Ensure path is safe.
            # /tmp/ is generally okay but consider placing in a more controlled directory if possible.
            # The filename itself is static here.
            temp_conf_file = "/tmp/hostapd_wpa3.conf" # Static filename
            with open(temp_conf_file, 'w') as f:
                f.write(config_content)
            
            # Start hostapd with WPA3 config
            cmd = ['hostapd', temp_conf_file, '-B'] # temp_conf_file is static
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                self.logger.info(f"WPA3 hotspot '{ssid}' configured successfully")
                return True
            else:
                self.logger.error(f"WPA3 hostapd command failed: {result.stderr}. Trying WPA2.")
                return self._configure_wpa2(ssid, password, interface) # Already validated inputs
                
        except Exception as e:
            self.logger.error(f"WPA3 configuration error: {e}")
            return False
    
    def _configure_mixed_wpa(self, ssid: str, password: str, interface: str) -> bool:
        """Configure mixed WPA2/WPA3 security"""
        # Inputs (ssid, password, interface) are assumed to be pre-validated.
        config_content = f"""interface={interface}
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
        temp_conf_file = "/tmp/hostapd_mixed.conf" # Static filename
        try:
            with open(temp_conf_file, 'w') as f:
                f.write(config_content)
            
            cmd = ['hostapd', temp_conf_file, '-B']
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                self.logger.error(f"Mixed WPA hostapd command failed: {result.stderr}")
                return False
            return True
            
        except Exception as e:
            self.logger.error(f"Mixed WPA configuration error: {e}")
            return False
    
    def _configure_open(self, ssid: str, interface: str) -> bool:
        """Configure open (no security) hotspot"""
        # Inputs (ssid, interface) are assumed to be pre-validated.
        try:
            safe_con_name_suffix = self.validator.validate(ssid, 'filename', context="sec_mgr_open_conname_suffix")
            con_name = f'hotspot-{safe_con_name_suffix}'
            cmd = [
                'nmcli', 'device', 'wifi', 'hotspot',
                'ifname', interface, # validated interface
                'con-name', con_name,
                'ssid', ssid         # validated ssid
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                self.logger.error(f"Open hotspot configuration failed: {result.stderr}")
                return False
            return True
            
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
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="sec_mgr_block_mac").upper()
        except ValidationError as e:
            self.logger.error(f"Invalid MAC address for blocking: {mac_address}. Error: {e}")
            return False

        try:
            self.blocked_devices.add(validated_mac)
            
            cmd = [
                'iptables', '-A', 'FORWARD',
                '-m', 'mac', '--mac-source', validated_mac,
                '-j', 'DROP'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                self.logger.info(f"Blocked device: {validated_mac}")
                return True
            else:
                self.logger.error(f"iptables block command failed for {validated_mac}: {result.stderr}")
                self.blocked_devices.discard(validated_mac) # Revert optimistic add
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to block device {validated_mac}: {e}")
            # Ensure state consistency if exception occurs after adding to set but before iptables
            self.blocked_devices.discard(validated_mac)
            return False
    
    def unblock_device(self, mac_address: str) -> bool:
        """Unblock a device by MAC address"""
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="sec_mgr_unblock_mac").upper()
        except ValidationError as e:
            self.logger.error(f"Invalid MAC address for unblocking: {mac_address}. Error: {e}")
            return False
            
        try:
            # Remove iptables rule (don't check=True, rule might not exist)
            cmd = [
                'iptables', '-D', 'FORWARD',
                '-m', 'mac', '--mac-source', validated_mac,
                '-j', 'DROP'
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            self.blocked_devices.discard(validated_mac) # Ensure it's removed from set
            self.logger.info(f"Unblocked device: {validated_mac}")
            return True # Assume success as the goal is for the rule not to be present
                
        except Exception as e:
            self.logger.error(f"Failed to unblock device {validated_mac}: {e}")
            return False
    
    def enable_whitelist_mode(self, allowed_macs: List[str]) -> bool:
        """Enable whitelist mode - only allow specified MAC addresses"""
        validated_allowed_macs = set()
        for mac in allowed_macs:
            try:
                validated_mac = self.validator.validate(mac, 'mac_address', context=f"sec_mgr_whitelist_mac_{mac}").upper()
                validated_allowed_macs.add(validated_mac)
            except ValidationError as e:
                self.logger.warning(f"Invalid MAC '{mac}' in whitelist, skipping. Error: {e}")
                # Decide if one invalid MAC should stop the whole operation
                # For now, we'll just skip invalid ones.

        if not validated_allowed_macs:
            self.logger.error("No valid MAC addresses provided for whitelist.")
            return False

        try:
            self.allowed_devices = validated_allowed_macs
            self.whitelist_mode = True
            
            # Block all devices first (static command)
            subprocess.run(['iptables', '-P', 'FORWARD', 'DROP'], capture_output=True, text=True, check=False)
            subprocess.run(['iptables', '-F', 'FORWARD'], capture_output=True, text=True, check=False) # Flush existing FORWARD rules
            
            # Allow specific MACs
            for v_mac in self.allowed_devices:
                cmd = [
                    'iptables', '-A', 'FORWARD', # Use -A to append, -I for insert at top
                    '-m', 'mac', '--mac-source', v_mac,
                    '-j', 'ACCEPT'
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=False) # Log errors if any
            
            self.logger.info(f"Whitelist mode enabled for {len(self.allowed_devices)} devices")
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
