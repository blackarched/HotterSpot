#!/usr/bin/env python3
"""
Configuration Manager Script for Hotspot Tool
Manages hotspot settings, profiles, and system configurations
"""

import json
import os
import configparser
from datetime import datetime
import subprocess
import platform

class ConfigManager:
    def __init__(self, config_dir='hotspot_config'):
        self.config_dir = config_dir
        self.main_config_file = os.path.join(config_dir, 'hotspot_config.json')
        self.profiles_file = os.path.join(config_dir, 'profiles.json')
        self.system_config_file = os.path.join(config_dir, 'system_config.json')
        
        # Create config directory
        os.makedirs(config_dir, exist_ok=True)
        
        # Load configurations
        self.config = self.load_main_config()
        self.profiles = self.load_profiles()
        self.system_config = self.load_system_config()
    
    def load_main_config(self):
        """Load main hotspot configuration"""
        default_config = {
            'ssid': 'MyHotspot',
            'password': 'password123',
            'security': 'WPA2',
            'channel': 6,
            'max_clients': 10,
            'hidden_ssid': False,
            'auto_start': False,
            'interface': 'wlan0',
            'ip_range': '192.168.4.1/24',
            'dhcp_start': '192.168.4.100',
            'dhcp_end': '192.168.4.200',
            'dns_servers': ['8.8.8.8', '8.8.4.4'],
            'bandwidth_limit': {
                'enabled': False,
                'upload_kbps': 1000,
                'download_kbps': 1000
            },
            'logging': {
                'enabled': True,
                'level': 'INFO',
                'file': 'hotspot.log'
            }
        }
        
        try:
            if os.path.exists(self.main_config_file):
                with open(self.main_config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to ensure all keys exist
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as e:
            print(f"Error loading main config: {e}")
        
        return default_config
    
    def load_profiles(self):
        """Load saved hotspot profiles"""
        try:
            if os.path.exists(self.profiles_file):
                with open(self.profiles_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading profiles: {e}")
        return {}
    
    def load_system_config(self):
        """Load system-specific configuration"""
        default_system_config = {
            'os_type': platform.system(),
            'startup_delay': 5,
            'network_interface': self.detect_wireless_interface(),
            'firewall_enabled': True,
            'nat_enabled': True,
            'ip_forwarding': True,
            'captive_portal': {
                'enabled': False,
                'port': 8080,
                'redirect_url': 'http://192.168.4.1:8080/login'
            },
            'monitoring': {
                'update_interval': 5,
                'save_statistics': True,
                'statistics_retention_days': 30
            },
            'security': {
                'mac_filtering': False,
                'access_control': False,
                'rate_limiting': False
            }
        }
        
        try:
            if os.path.exists(self.system_config_file):
                with open(self.system_config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults
                for key, value in default_system_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as e:
            print(f"Error loading system config: {e}")
        
        return default_system_config
    
    def detect_wireless_interface(self):
        """Detect available wireless interfaces"""
        try:
            if platform.system() == 'Linux':
                result = subprocess.run(['iwconfig'], capture_output=True, text=True)
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'IEEE 802.11' in line:
                            interface = line.split()[0]
                            return interface
            elif platform.system() == 'Windows':
                result = subprocess.run(['netsh', 'wlan', 'show', 'profiles'], 
                                      capture_output=True, text=True)
                # Windows detection logic would go here
                return 'WiFi'
        except Exception:
            pass
        
        # Default fallbacks
        if platform.system() == 'Linux':
            return 'wlan0'
        else:
            return 'WiFi'
    
    def save_main_config(self):
        """Save main configuration to file"""
        try:
            self.config['last_modified'] = datetime.now().isoformat()
            with open(self.main_config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving main config: {e}")
            return False
    
    def save_profiles(self):
        """Save profiles to file"""
        try:
            with open(self.profiles_file, 'w') as f:
                json.dump(self.profiles, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving profiles: {e}")
            return False
    
    def save_system_config(self):
        """Save system configuration to file"""
        try:
            with open(self.system_config_file, 'w') as f:
                json.dump(self.system_config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving system config: {e}")
            return False
    
    def update_config(self, **kwargs):
        """Update main configuration with new values"""
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value
            else:
                print(f"Warning: Unknown config key '{key}'")
        
        return self.save_main_config()
    
    def get_config(self, key=None):
        """Get configuration value(s)"""
        if key:
            return self.config.get(key)
        return self.config.copy()
    
    def validate_config(self):
        """Validate current configuration"""
        errors = []
        warnings = []
        
        # Validate SSID
        if not self.config['ssid'] or len(self.config['ssid']) > 32:
            errors.append("SSID must be between 1-32 characters")
        
        # Validate password
        if len(self.config['password']) < 8:
            errors.append("Password must be at least 8 characters")
        
        # Validate channel
        if not (1 <= self.config['channel'] <= 14):
            warnings.append("Channel should be between 1-14")
        
        # Validate IP range
        try:
            import ipaddress
            ipaddress.ip_network(self.config['ip_range'])
        except:
            errors.append("Invalid IP range format")
        
        # Validate max clients
        if not (1 <= self.config['max_clients'] <= 50):
            warnings.append("Max clients should be between 1-50")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def create_profile(self, name, description="", config_override=None):
        """Create a new hotspot profile"""
        if config_override:
            profile_config = config_override.copy()
        else:
            profile_config = self.config.copy()
        
        profile = {
            'name': name,
            'description': description,
            'config': profile_config,
            'created': datetime.now().isoformat(),
            'last_used': None
        }
        
        self.profiles[name] = profile
        return self.save_profiles()
    
    def load_profile(self, name):
        """Load a hotspot profile"""
        if name not in self.profiles:
            return False
        
        profile = self.profiles[name]
        self.config = profile['config'].copy()
        
        # Update last used timestamp
        profile['last_used'] = datetime.now().isoformat()
        self.save_profiles()
        self.save_main_config()
        
        return True
    
    def delete_profile(self, name):
        """Delete a hotspot profile"""
        if name in self.profiles:
            del self.profiles[name]
            return self.save_profiles()
        return False
    
    def list_profiles(self):
        """List all available profiles"""
        return list(self.profiles.keys())
    
    def get_profile(self, name):
        """Get profile details"""
        return self.profiles.get(name)
    
    def export_config(self, filename):
        """Export configuration to file"""
        export_data = {
            'main_config': self.config,
            'profiles': self.profiles,
            'system_config': self.system_config,
            'export_time': datetime.now().isoformat(),
            'version': '1.0'
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error exporting config: {e}")
            return False
    
    def import_config(self, filename):
        """Import configuration from file"""
        try:
            with open(filename, 'r') as f:
                import_data = json.load(f)
            
            # Validate import data
            if 'main_config' not in import_data:
                return False, "Invalid config file format"
            
            # Backup current configs
            backup_suffix = datetime.now().strftime("_%Y%m%d_%H%M%S")
            self.export_config(f"backup_config{backup_suffix}.json")
            
            # Import configurations
            if 'main_config' in import_data:
                self.config = import_data['main_config']
                self.save_main_config()
            
            if 'profiles' in import_data:
                self.profiles.update(import_data['profiles'])
                self.save_profiles()
            
            if 'system_config' in import_data:
                self.system_config.update(import_data['system_config'])
                self.save_system_config()
            
            return True, "Configuration imported successfully"
            
        except Exception as e:
            return False, f"Error importing config: {e}"
    
    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        # Backup current config
        backup_suffix = datetime.now().strftime("_%Y%m%d_%H%M%S")
        self.export_config(f"reset_backup{backup_suffix}.json")
        
        # Reset to defaults
        self.config = self.load_main_config()
        self.system_config = self.load_system_config()
        
        # Clear config files to force defaults
        try:
            if os.path.exists(self.main_config_file):
                os.remove(self.main_config_file)
            if os.path.exists(self.system_config_file):
                os.remove(self.system_config_file)
        except:
            pass
        
        # Reload defaults
        self.config = self.load_main_config()
        self.system_config = self.load_system_config()
        
        # Save new defaults
        self.save_main_config()
        self.save_system_config()
        
        return True
    
    def generate_hostapd_config(self):
        """Generate hostapd configuration for Linux"""
        config_lines = [
            f"interface={self.config['interface']}",
            f"driver=nl80211",
            f"ssid={self.config['ssid']}",
            f"hw_mode=g",
            f"channel={self.config['channel']}",
            f"wmm_enabled=0",
            f"macaddr_acl=0",
            f"auth_algs=1",
            f"ignore_broadcast_ssid={'1' if self.config['hidden_ssid'] else '0'}",
            f"wpa=2",
            f"wpa_passphrase={self.config['password']}",
            f"wpa_key_mgmt=WPA-PSK",
            f"wpa_pairwise=TKIP",
            f"rsn_pairwise=CCMP"
        ]
        
        return '\n'.join(config_lines)
    
    def generate_dnsmasq_config(self):
        """Generate dnsmasq configuration for Linux"""
        config_lines = [
            f"interface={self.config['interface']}",
            f"dhcp-range={self.config['dhcp_start']},{self.config['dhcp_end']},255.255.255.0,24h",
            "dhcp-option=3,192.168.4.1",  # Default gateway
            f"dhcp-option=6,{','.join(self.config['dns_servers'])}",  # DNS servers
            "server=8.8.8.8",
            "log-queries",
            "log-dhcp",
            "listen-address=127.0.0.1"
        ]
        
        return '\n'.join(config_lines)
    
    def get_system_requirements(self):
        """Get system requirements and current status"""
        requirements = {
            'linux': {
                'packages': ['hostapd', 'dnsmasq', 'iptables'],
                'services': ['hostapd', 'dnsmasq'],
                'kernel_modules': ['mac80211', 'cfg80211'],
                'permissions': ['sudo access required']
            },
            'windows': {
                'features': ['ICS (Internet Connection Sharing)', 'Hosted Network Support'],
                'permissions': ['Administrator access required'],
                'limitations': ['Limited device management', 'No direct bandwidth control']
            }
        }
        
        os_type = platform.system().lower()
        return requirements.get(os_type, {})

def main():
    """Main function for configuration management"""
    config_manager = ConfigManager()
    
    while True:
        print("\n--- Configuration Manager ---")
        print("1. View current config")
        print("2. Update config")
        print("3. Validate config")
        print("4. Create profile")
        print("5. Load profile")
        print("6. List profiles")
        print("7. Delete profile")
        print("8. Export config")
        print("9. Import config")
        print("10. Reset to defaults")
        print("11. Generate hostapd config")
        print("12. Generate dnsmasq config")
        print("0. Exit")
        
        choice = input("Select option: ").strip()
        
        if choice == '1':
            config = config_manager.get_config()
            print(json.dumps(config, indent=2))
        
        elif choice == '2':
            print("Enter new values (press Enter to skip):")
            ssid = input(f"SSID [{config_manager.config['ssid']}]: ").strip()
            password = input(f"Password [{config_manager.config['password']}]: ").strip()
            channel = input(f"Channel [{config_manager.config['channel']}]: ").strip()
            
            updates = {}
            if ssid:
                updates['ssid'] = ssid
            if password:
                updates['password'] = password
            if channel:
                try:
                    updates['channel'] = int(channel)
                except ValueError:
                    print("Invalid channel number")
            
            if updates:
                if config_manager.update_config(**updates):
                    print("Configuration updated successfully")
                else:
                    print("Error updating configuration")
        
        elif choice == '3':
            validation = config_manager.validate_config()
            print(f"Valid: {validation['valid']}")
            if validation['errors']:
                print("Errors:")
                for error in validation['errors']:
                    print(f"  - {error}")
            if validation['warnings']:
                print("Warnings:")
                for warning in validation['warnings']:
                    print(f"  - {warning}")
        
        elif choice == '4':
            name = input("Profile name: ").strip()
            description = input("Description (optional): ").strip()
            if config_manager.create_profile(name, description):
                print(f"Profile '{name}' created successfully")
            else:
                print("Error creating profile")
        
        elif choice == '5':
            profiles = config_manager.list_profiles()
            if not profiles:
                print("No profiles available")
                continue
            
            print("Available profiles:")
            for i, profile in enumerate(profiles, 1):
                print(f"  {i}. {profile}")
            
            try:
                index = int(input("Select profile number: ")) - 1
                if 0 <= index < len(profiles):
                    if config_manager.load_profile(profiles[index]):
                        print(f"Profile '{profiles[index]}' loaded successfully")
                    else:
                        print("Error loading profile")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Invalid input")
        
        elif choice == '6':
            profiles = config_manager.list_profiles()
            if profiles:
                print("Available profiles:")
                for profile in profiles:
                    profile_data = config_manager.get_profile(profile)
                    print(f"  - {profile}: {profile_data.get('description', 'No description')}")
            else:
                print("No profiles available")
        
        elif choice == '7':
            profile_name = input("Profile name to delete: ").strip()
            if config_manager.delete_profile(profile_name):
                print(f"Profile '{profile_name}' deleted successfully")
            else:
                print("Profile not found or error deleting")
        
        elif choice == '8':
            filename = input("Export filename: ").strip()
            if config_manager.export_config(filename):
                print(f"Configuration exported to {filename}")
            else:
                print("Error exporting configuration")
        
        elif choice == '9':
            filename = input("Import filename: ").strip()
            success, message = config_manager.import_config(filename)
            print(message)
        
        elif choice == '10':
            confirm = input("Reset to defaults? This will backup current config. (y/N): ").strip().lower()
            if confirm == 'y':
                if config_manager.reset_to_defaults():
                    print("Configuration reset to defaults")
                else:
                    print("Error resetting configuration")
        
        elif choice == '11':
            hostapd_config = config_manager.generate_hostapd_config()
            print("Generated hostapd configuration:")
            print(hostapd_config)
        
        elif choice == '12':
            dnsmasq_config = config_manager.generate_dnsmasq_config()
            print("Generated dnsmasq configuration:")
            print(dnsmasq_config)
        
        elif choice == '0':
            break

if __name__ == "__main__":
    main()