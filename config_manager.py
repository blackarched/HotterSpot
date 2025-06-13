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
import secrets
import string
from input_validator import get_validator, ValidationError

class ConfigManager:
    def __init__(self, config_dir='hotspot_config'):
        self.validator = get_validator()
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

    def _generate_secure_password(self, length=12):
        """Generates a secure random password."""
        alphabet = string.ascii_letters + string.digits + string.punctuation
        # Ensure the alphabet contains characters for each category to avoid infinite loop
        # if length is too small (e.g. length < 4 for all categories)
        if length < 4: # Basic check, can be more sophisticated
            print("Warning: Password length is too short for strong complexity. Consider a length of 8 or more.")
            # Fallback to simpler generation if length is too short for category checks
            return ''.join(secrets.choice(alphabet) for _ in range(length))

        while True:
            password = ''.join(secrets.choice(alphabet) for _ in range(length))
            # Ensure it has a mix of character types
            if (any(c.islower() for c in password)
                    and any(c.isupper() for c in password)
                    and any(c.isdigit() for c in password)
                    and any(c in string.punctuation for c in password)):
                break
        return password
    
    def load_main_config(self):
        """Load main hotspot configuration"""
        default_config = {
            'ssid': 'MyHotspot',
            # 'password': 'password123', # Password will be handled separately
            'password': None, # Placeholder for password
            'security': 'WPA2',
            'channel': 6,
            'max_clients': 10,
            'hidden_ssid': False,
            'auto_start': False,
            'interface': 'wlan0',
            'ip_range': '192.168.4.0/24', # Corrected network address
            'hotspot_ip': '192.168.4.1', # Added for explicit gateway/dnsmasq listen IP
            'dhcp_start': '192.168.4.100',
            'dhcp_end': '192.168.4.200',
            'dhcp_lease_time': '24h', # Added
            'dns_servers': ['8.8.8.8', '8.8.4.4'], # Upstream DNS
            'blocked_domains': [], # Added for domain blocking
            'dnsmasq_lease_file': '/tmp/hotterspot.leases', # Added default path for lease file
            'dnsmasq_extra_options': [], # For custom dnsmasq directives
            'captive_portal_enabled': False, # To control address=/#/ rule
            'local_domain_name': 'hotspot.local', # Optional local domain
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
        

        config_loaded_from_file = False
        loaded_config = {}


        main_config_rules = {
            'ssid': 'ssid',
            'password': 'password', # Validates if a password string exists and meets basic criteria
            'security': 'user_input', # Basic check, could be more specific (e.g. enum WPA2/WPA3)
            'channel': 'port', # Ensures it's a number in port range; actual valid channels are 1-14
            'max_clients': 'port', # Ensures it's a number
            'hidden_ssid': 'user_input', # Expects boolean, JSON loads as bool.
            'auto_start': 'user_input', # Expects boolean
            'interface': 'interface',
            'ip_range': 'user_input',
            'hotspot_ip': 'ip_address',
            'dhcp_start': 'ip_address',
            'dhcp_end': 'ip_address',
            'dhcp_lease_time': 'user_input', # e.g. "12h", "1d"
            # dns_servers is a list
            # blocked_domains is a list
            'dnsmasq_lease_file': 'filename', # Validate as a path/filename
            # dnsmasq_extra_options is a list of strings.
            'captive_portal_enabled': 'user_input', # boolean
            'local_domain_name': 'user_input', # or a 'hostname' like rule if available
            # bandwidth_limit and logging are dicts, would need separate validation or rule enhancements.
        }

        try:
            if os.path.exists(self.main_config_file):
                with open(self.main_config_file, 'r') as f:
                    loaded_config_from_json = json.load(f)

                try:
                    # Validate only the fields present in the JSON that have rules
                    # For nested dicts, this basic validation won't recurse unless handled explicitly
                    partial_rules = {k: v for k, v in main_config_rules.items() if k in loaded_config_from_json}
                    validated_json_data = self.validator.validate_batch(
                        {k: loaded_config_from_json[k] for k in partial_rules.keys()},
                        partial_rules,
                        context="main_config_from_file"
                    )
                    # Update loaded_config_from_json with validated values (e.g. type conversions like port string to int)
                    for key, validated_value in validated_json_data.items():
                        loaded_config_from_json[key] = validated_value
                    loaded_config = loaded_config_from_json

                except ValidationError as ve:
                    print(f"Warning: Invalid data found in {self.main_config_file}. Some settings may use defaults or previous valid values. Error: {ve}")
                    # Fallback strategy: try to use defaults for the whole config if critical fields fail,
                    # or proceed with loaded_config and let default merging fix missing/failed fields.
                    # For now, we'll let it proceed and default merging will apply.
                    # A more robust approach might involve removing only offending keys or using defaults more aggressively.
                    loaded_config = loaded_config_from_json # Use original loaded if validation fails, let defaults merge

                config_loaded_from_file = True
                # Merge with defaults to ensure all keys exist, loaded values take precedence
                # except for password which we will handle specifically
                temp_default_copy = default_config.copy()
                if 'password' in temp_default_copy: # Don't overwrite loaded password with default None yet
                    del temp_default_copy['password']

                for key, value in temp_default_copy.items():
                    if key not in loaded_config:
                        loaded_config[key] = value
            else: # File does not exist, use defaults
                loaded_config = default_config.copy() # Make a copy to modify
                config_loaded_from_file = False # Explicitly set for password logic

        except json.JSONDecodeError as jde:
            print(f"Error decoding JSON from {self.main_config_file}: {jde}. Using default configuration.")
            loaded_config = default_config.copy()
            config_loaded_from_file = False
        except Exception as e: # Catch other potential errors like permission issues
            print(f"Error loading main config file {self.main_config_file}: {e}. Using default configuration.")
            loaded_config = default_config.copy()
            config_loaded_from_file = False

        # Password handling logic
        generate_new_password = False
        current_password = loaded_config.get('password')

        if config_loaded_from_file:
            # Case 1: File was loaded. Check if password is the old default or missing.
            if current_password == "password123" or current_password is None:
                generate_new_password = True
        else:
            # Case 2: File not loaded (first run or error), so definitely generate.
            generate_new_password = True

        if generate_new_password:
            new_password = self._generate_secure_password()
            loaded_config['password'] = new_password
            # Ensure this message is clearly visible. In a real app, this would be a GUI notification.
            print(f"IMPORTANT: A new secure default password has been generated: {new_password}")
            print("This password is for the hotspot. Please note it down or change it via the application.")
            # If the config was initially loaded from file and we changed the password,
            # it should be saved back. The caller of load_main_config (constructor)
            # will then call save_main_config if needed.
            # However, the current structure calls load_main_config in __init__ and then assigns to self.config
            # The save is typically triggered by an explicit user action or when the app closes.
            # Forcing a save here might be unexpected. Let's assume the main app will save it.
            # For now, we ensure self.config (which will be this loaded_config) has the new password.

        # Validate nested dictionaries if they exist
        if 'bandwidth_limit' in loaded_config and isinstance(loaded_config['bandwidth_limit'], dict):
            bw_rules = {'enabled': 'user_input', 'upload_kbps': 'port', 'download_kbps': 'port'}
            try:
                validated_bw = self.validator.validate_batch(loaded_config['bandwidth_limit'], bw_rules, context="main_config.bandwidth_limit")
                loaded_config['bandwidth_limit'] = validated_bw
            except ValidationError as ve:
                print(f"Warning: Invalid data in 'bandwidth_limit' section of main config. Using defaults for this section. Error: {ve}")
                loaded_config['bandwidth_limit'] = default_config['bandwidth_limit'].copy()

        if 'logging' in loaded_config and isinstance(loaded_config['logging'], dict):
            log_rules = {'enabled': 'user_input', 'level': 'user_input', 'file': 'filename'}
            try:
                validated_log = self.validator.validate_batch(loaded_config['logging'], log_rules, context="main_config.logging")
                loaded_config['logging'] = validated_log
            except ValidationError as ve:
                print(f"Warning: Invalid data in 'logging' section of main config. Using defaults for this section. Error: {ve}")
                loaded_config['logging'] = default_config['logging'].copy()

        # If password was valid and not the old default, it's retained from loaded_config.
        return loaded_config
    
    def load_profiles(self):
        """Load saved hotspot profiles"""
        profiles_config_rules = { # Same as main_config_rules for profile configs
            'ssid': 'ssid', 'password': 'password', 'security': 'user_input',
            'channel': 'port', 'max_clients': 'port', 'hidden_ssid': 'user_input',
            'auto_start': 'user_input', 'interface': 'interface', 'ip_range': 'user_input',
            'dhcp_start': 'ip_address', 'dhcp_end': 'ip_address',
        }
        profiles = {}
        if os.path.exists(self.profiles_file):
            try:
                with open(self.profiles_file, 'r') as f:
                    loaded_profiles = json.load(f)

                for profile_name, profile_data in loaded_profiles.items():
                    if isinstance(profile_data, dict) and 'config' in profile_data and isinstance(profile_data['config'], dict):
                        try:
                            # Validate only the fields present in the profile's config that have rules
                            current_profile_config = profile_data['config']
                            partial_rules = {k: v for k, v in profiles_config_rules.items() if k in current_profile_config}

                            validated_profile_config_data = self.validator.validate_batch(
                                {k: current_profile_config[k] for k in partial_rules.keys()},
                                partial_rules,
                                context=f"profile_{profile_name}"
                            )
                            # Update profile_data['config'] with validated values
                            for key, validated_value in validated_profile_config_data.items():
                                profile_data['config'][key] = validated_value

                            # Validate nested dictionaries (bandwidth_limit, logging) for each profile
                            if 'bandwidth_limit' in profile_data['config'] and isinstance(profile_data['config']['bandwidth_limit'], dict):
                                bw_rules = {'enabled': 'user_input', 'upload_kbps': 'port', 'download_kbps': 'port'}
                                try:
                                    validated_bw = self.validator.validate_batch(profile_data['config']['bandwidth_limit'], bw_rules, context=f"profile_{profile_name}.bandwidth_limit")
                                    profile_data['config']['bandwidth_limit'] = validated_bw
                                except ValidationError as ve_bw:
                                    print(f"Warning: Invalid data in 'bandwidth_limit' for profile '{profile_name}'. Error: {ve_bw}")
                                    # Optionally reset this part to a default or remove it

                            if 'logging' in profile_data['config'] and isinstance(profile_data['config']['logging'], dict):
                                log_rules = {'enabled': 'user_input', 'level': 'user_input', 'file': 'filename'}
                                try:
                                    validated_log = self.validator.validate_batch(profile_data['config']['logging'], log_rules, context=f"profile_{profile_name}.logging")
                                    profile_data['config']['logging'] = validated_log
                                except ValidationError as ve_log:
                                     print(f"Warning: Invalid data in 'logging' for profile '{profile_name}'. Error: {ve_log}")

                            profiles[profile_name] = profile_data # Add validated (or partially validated) profile
                        except ValidationError as ve:
                            print(f"Warning: Invalid data in configuration for profile '{profile_name}'. This profile may not load correctly or be skipped. Error: {ve}")
                            # Optionally skip adding this profile: continue
                        except Exception as ex_profile: # Catch other errors during profile processing
                            print(f"Error processing profile '{profile_name}': {ex_profile}. Skipping this profile.")
                    else:
                        print(f"Warning: Profile '{profile_name}' has an invalid structure. Skipping.")
            except json.JSONDecodeError as jde:
                print(f"Error decoding JSON from {self.profiles_file}: {jde}. No profiles loaded.")
            except Exception as e:
                print(f"Error loading profiles from {self.profiles_file}: {e}. No profiles loaded.")
        return profiles
    
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
        

        system_config_rules = {
            'os_type': 'user_input', # Could be more specific if needed
            'startup_delay': 'port',
            'network_interface': 'interface',
            'firewall_enabled': 'user_input', # Boolean
            'nat_enabled': 'user_input', # Boolean
            'ip_forwarding': 'user_input', # Boolean
            # captive_portal, monitoring, security are dicts
        }
        loaded_config = {}

        try:
            if os.path.exists(self.system_config_file):
                with open(self.system_config_file, 'r') as f:
                    loaded_config_from_json = json.load(f)

                try:
                    partial_rules = {k: v for k, v in system_config_rules.items() if k in loaded_config_from_json}
                    validated_json_data = self.validator.validate_batch(
                         {k: loaded_config_from_json[k] for k in partial_rules.keys()},
                        partial_rules,
                        context="system_config_from_file"
                    )
                    for key, validated_value in validated_json_data.items():
                        loaded_config_from_json[key] = validated_value
                    loaded_config = loaded_config_from_json

                except ValidationError as ve:
                    print(f"Warning: Invalid data found in {self.system_config_file}. Some settings may use defaults. Error: {ve}")
                    loaded_config = loaded_config_from_json # Use original, let defaults merge

                # Merge with defaults to ensure all keys exist
                final_config = default_system_config.copy()
                final_config.update(loaded_config) # Validated and loaded data takes precedence
                loaded_config = final_config
            else:
                loaded_config = default_system_config.copy()

        except json.JSONDecodeError as jde:
            print(f"Error decoding JSON from {self.system_config_file}: {jde}. Using default system configuration.")
            loaded_config = default_system_config.copy()
        except Exception as e:
            print(f"Error loading system config file {self.system_config_file}: {e}. Using default system configuration.")
            loaded_config = default_system_config.copy()

        # Validate nested dictionaries
        if 'captive_portal' in loaded_config and isinstance(loaded_config['captive_portal'], dict):
            cp_rules = {'enabled': 'user_input', 'port': 'port', 'redirect_url': 'user_input'}
            try:
                validated_cp = self.validator.validate_batch(loaded_config['captive_portal'], cp_rules, context="system_config.captive_portal")
                loaded_config['captive_portal'] = validated_cp
            except ValidationError as ve:
                print(f"Warning: Invalid data in 'captive_portal' section of system config. Using defaults. Error: {ve}")
                loaded_config['captive_portal'] = default_system_config['captive_portal'].copy()

        if 'monitoring' in loaded_config and isinstance(loaded_config['monitoring'], dict):
            mon_rules = {'update_interval': 'port', 'save_statistics': 'user_input', 'statistics_retention_days': 'port'}
            try:
                validated_mon = self.validator.validate_batch(loaded_config['monitoring'], mon_rules, context="system_config.monitoring")
                loaded_config['monitoring'] = validated_mon
            except ValidationError as ve:
                print(f"Warning: Invalid data in 'monitoring' section of system config. Using defaults. Error: {ve}")
                loaded_config['monitoring'] = default_system_config['monitoring'].copy()

        if 'security' in loaded_config and isinstance(loaded_config['security'], dict):
            sec_rules = {'mac_filtering': 'user_input', 'access_control': 'user_input', 'rate_limiting': 'user_input'}
            try:
                validated_sec = self.validator.validate_batch(loaded_config['security'], sec_rules, context="system_config.security")
                loaded_config['security'] = validated_sec
            except ValidationError as ve:
                print(f"Warning: Invalid data in 'security' section of system config. Using defaults. Error: {ve}")
                loaded_config['security'] = default_system_config['security'].copy()

        return loaded_config
    
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
            if not isinstance(import_data, dict) or 'main_config' not in import_data:
                return False, "Invalid config file format: 'main_config' key is missing or data is not a dictionary."

            main_config_rules = {
                'ssid': 'ssid', 'password': 'password', 'security': 'user_input',
                'channel': 'port', 'max_clients': 'port', 'hidden_ssid': 'user_input',
                'auto_start': 'user_input', 'interface': 'interface', 'ip_range': 'user_input',
                'dhcp_start': 'ip_address', 'dhcp_end': 'ip_address',
            }
            system_config_rules = {
                'os_type': 'user_input', 'startup_delay': 'port', 'network_interface': 'interface',
                'firewall_enabled': 'user_input', 'nat_enabled': 'user_input', 'ip_forwarding': 'user_input',
            }
            # Nested dict rules for sub-sections
            bw_rules = {'enabled': 'user_input', 'upload_kbps': 'port', 'download_kbps': 'port'}
            log_rules = {'enabled': 'user_input', 'level': 'user_input', 'file': 'filename'}
            cp_rules = {'enabled': 'user_input', 'port': 'port', 'redirect_url': 'user_input'}
            mon_rules = {'update_interval': 'port', 'save_statistics': 'user_input', 'statistics_retention_days': 'port'}
            sec_rules = {'mac_filtering': 'user_input', 'access_control': 'user_input', 'rate_limiting': 'user_input'}

            try:
                # Validate main_config
                imported_main_config = import_data.get('main_config', {})
                if not isinstance(imported_main_config, dict): return False, "Imported 'main_config' must be a dictionary."
                partial_main_rules = {k: v for k, v in main_config_rules.items() if k in imported_main_config}
                self.validator.validate_batch(imported_main_config, partial_main_rules, context="imported_main_config")
                if 'bandwidth_limit' in imported_main_config and isinstance(imported_main_config['bandwidth_limit'], dict):
                    self.validator.validate_batch(imported_main_config['bandwidth_limit'], bw_rules, context="imported_main_config.bandwidth_limit")
                if 'logging' in imported_main_config and isinstance(imported_main_config['logging'], dict):
                     self.validator.validate_batch(imported_main_config['logging'], log_rules, context="imported_main_config.logging")


                # Validate profiles
                imported_profiles = import_data.get('profiles', {})
                if not isinstance(imported_profiles, dict): return False, "Imported 'profiles' must be a dictionary."
                for profile_name, profile_data in imported_profiles.items():
                    if not isinstance(profile_data, dict) or 'config' not in profile_data or not isinstance(profile_data['config'], dict):
                        return False, f"Profile '{profile_name}' is malformed."
                    profile_config = profile_data['config']
                    partial_profile_rules = {k: v for k, v in main_config_rules.items() if k in profile_config}
                    self.validator.validate_batch(profile_config, partial_profile_rules, context=f"imported_profile_{profile_name}")
                    if 'bandwidth_limit' in profile_config and isinstance(profile_config['bandwidth_limit'], dict):
                        self.validator.validate_batch(profile_config['bandwidth_limit'], bw_rules, context=f"imported_profile_{profile_name}.bandwidth_limit")
                    if 'logging' in profile_config and isinstance(profile_config['logging'], dict):
                        self.validator.validate_batch(profile_config['logging'], log_rules, context=f"imported_profile_{profile_name}.logging")

                # Validate system_config
                imported_system_config = import_data.get('system_config', {})
                if not isinstance(imported_system_config, dict): return False, "Imported 'system_config' must be a dictionary."
                partial_system_rules = {k: v for k, v in system_config_rules.items() if k in imported_system_config}
                self.validator.validate_batch(imported_system_config, partial_system_rules, context="imported_system_config")
                if 'captive_portal' in imported_system_config and isinstance(imported_system_config['captive_portal'], dict):
                    self.validator.validate_batch(imported_system_config['captive_portal'], cp_rules, context="imported_system_config.captive_portal")
                if 'monitoring' in imported_system_config and isinstance(imported_system_config['monitoring'], dict):
                    self.validator.validate_batch(imported_system_config['monitoring'], mon_rules, context="imported_system_config.monitoring")
                if 'security' in imported_system_config and isinstance(imported_system_config['security'], dict):
                    self.validator.validate_batch(imported_system_config['security'], sec_rules, context="imported_system_config.security")

            except ValidationError as ve:
                return False, f"Imported configuration contains invalid data: {ve}"

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
            f"interface={self.config.get('interface', 'wlan0')}",
            f"dhcp-range={self.config.get('dhcp_start', '192.168.4.100')},{self.config.get('dhcp_end', '192.168.4.200')},{self.config.get('dhcp_lease_time', '24h')}",
            f"dhcp-option=option:router,{self.config.get('hotspot_ip', '192.168.4.1')}",
            # If dnsmasq is the sole DNS for clients (e.g. for captive portal), it should offer its own IP.
            # Otherwise, offer upstream DNS directly.
            f"dhcp-option=option:dns-server,{self.config.get('hotspot_ip', '192.168.4.1')}",
            f"listen-address=127.0.0.1,{self.config.get('hotspot_ip', '192.168.4.1')}",
            "domain-needed",  # Don't forward short names
            "bogus-priv",     # Don't forward reverse lookups for private ranges
            "expand-hosts",   # Expand simple hostnames with local domain
            "log-queries",    # Optional: for debugging
            "log-dhcp"        # Optional: for debugging
        ]

        # Upstream DNS servers for dnsmasq to use
        upstream_dns = self.config.get('dns_servers', ['8.8.8.8', '8.8.4.4'])
        if upstream_dns: # Ensure it's not an empty list
            for server_ip in upstream_dns:
                # Validate each server_ip before adding it
                try:
                    validated_dns_ip = self.validator.validate(server_ip, 'ip_address', context="dnsmasq_upstream_dns")
                    config_lines.append(f"server={validated_dns_ip}")
                except ValidationError:
                    print(f"Warning: Invalid upstream DNS server IP '{server_ip}' in config, skipping.")
        else: # Fallback if no upstream DNS is provided, use a common one
             config_lines.append(f"server=8.8.8.8")


        local_domain = self.config.get('local_domain_name')
        if local_domain:
            try: # Use 'user_input' for basic validation, a 'hostname' or 'domain' rule would be better
                validated_local_domain = self.validator.validate(local_domain, 'user_input', context="dnsmasq_local_domain")
                config_lines.append(f"local=/{validated_local_domain}/")
                config_lines.append(f"domain={validated_local_domain}") # Define the local domain
            except ValidationError:
                print(f"Warning: Invalid local_domain_name '{local_domain}' in config, skipping.")

        if self.config.get('captive_portal_enabled', False):
            # Redirect all DNS queries for non-local domains to the hotspot's IP,
            # which is crucial for forcing clients to the captive portal page.
            config_lines.append(f"address=/#/{self.config.get('hotspot_ip', '192.168.4.1')}")

        # Add blocked domains
        blocked_domains_list = self.config.get('blocked_domains', [])
        if isinstance(blocked_domains_list, list):
            for domain in blocked_domains_list:
                if isinstance(domain, str) and domain.strip():
                    try:
                        # Use 'user_input' for basic validation, a specific 'domain_name' rule would be better.
                        validated_domain = self.validator.validate(domain, 'user_input', context="dnsmasq_blocked_domain")
                        config_lines.append(f"address=/{validated_domain}/0.0.0.0")
                    except ValidationError:
                        print(f"Warning: Invalid domain '{domain}' in blocked_domains list, skipping.")

        # Add any custom/extra dnsmasq options from config
        extra_options = self.config.get('dnsmasq_extra_options', [])
        if isinstance(extra_options, list):
            for option_line in extra_options:
                if isinstance(option_line, str) and option_line.strip(): # Basic check
                    # Further validation of option_line might be needed if it's complex
                    config_lines.append(option_line)

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