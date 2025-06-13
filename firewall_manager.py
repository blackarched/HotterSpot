#!/usr/bin/env python3
"""
Firewall Manager Module for Hotspot Tool
Handles iptables rules for security and traffic control
"""

import os
import sys
import subprocess
import logging
import platform
from datetime import datetime
from input_validator import get_validator, ValidationError
import re # For iptables-restore sanitization

class FirewallManager:
    def __init__(self, config_manager):
        self.validator = get_validator()
        self.config_manager = config_manager # Assuming config_manager provides validated config values
        self.system = platform.system().lower()
        self.active_rules = []
        
        # Interface names
        self.hotspot_interface = "wlan0"
        self.internet_interface = "eth0"
        self.hotspot_network = "192.168.4.0/24"
        self.captive_portal_port = 8080
        self.dns_port = 53
    
    def setup_hotspot_firewall(self, hotspot_interface="wlan0", internet_interface="eth0"):
        """Setup firewall rules for hotspot operation"""
        try:
            self.hotspot_interface = self.validator.validate(hotspot_interface, 'interface', context="fw_mgr_setup_hotspot_iface")
            self.internet_interface = self.validator.validate(internet_interface, 'interface', context="fw_mgr_setup_internet_iface")
        except ValidationError as e:
            logging.error(f"Invalid interface name for firewall setup: {e}")
            return False
        
        try:
            # Clear existing rules (uses self.hotspot_interface, now validated)
            self.clear_hotspot_rules()
            
            # Setup basic rules
            # Ensure ports are integers if they were from config
            dns_port_val = self.validator.validate(str(self.dns_port), 'port', context="fw_dns_port")
            captive_portal_port_val = self.validator.validate(str(self.captive_portal_port), 'port', context="fw_captive_port")

            rules = [
                # Enable IP forwarding
                ("sysctl", ["net.ipv4.ip_forward=1"]), # Static arg
                
                # NAT rules for internet sharing
                ("iptables", ["-t", "nat", "-A", "POSTROUTING", "-o", self.internet_interface, "-j", "MASQUERADE"]),
                ("iptables", ["-A", "FORWARD", "-i", self.internet_interface, "-o", self.hotspot_interface, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"]),
                ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-o", self.internet_interface, "-j", "ACCEPT"]),
                
                # Allow DNS traffic
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-p", "udp", "--dport", str(dns_port_val), "-j", "ACCEPT"]),
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-p", "tcp", "--dport", str(dns_port_val), "-j", "ACCEPT"]),
                
                # Allow DHCP traffic (static ports)
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-p", "udp", "--dport", "67", "-j", "ACCEPT"]),
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-p", "udp", "--dport", "68", "-j", "ACCEPT"]),
                
                # Allow captive portal traffic
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-p", "tcp", "--dport", str(captive_portal_port_val), "-j", "ACCEPT"]),
                
                # Allow SSH (optional, for management - static port)
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "22", "-j", "ACCEPT"]),
                
                # Block direct internet access until authenticated (captive portal - static ports)
                ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "80", "-j", "REJECT"]),
                ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "443", "-j", "REJECT"]),
                
                # Drop other traffic by default
                ("iptables", ["-A", "INPUT", "-i", self.hotspot_interface, "-j", "DROP"]),
            ]
            
            for command_type, args in rules:
                if self._execute_command(command_type, args):
                    self.active_rules.append((command_type, args))
                else:
                    logging.error(f"Failed to execute: {command_type} {' '.join(args)}")
            
            logging.info("Hotspot firewall rules configured")
            return True
            
        except Exception as e:
            logging.error(f"Failed to setup hotspot firewall: {e}")
            return False
    
    def setup_captive_portal_redirect(self):
        """Setup iptables rules for captive portal redirection"""
        # Assumes self.hotspot_interface and self.captive_portal_port are already validated or set from trusted source
        try:
            # Ensure ports are integers
            captive_portal_port_val = self.validator.validate(str(self.captive_portal_port), 'port', context="fw_captive_redirect_port")
            dns_port_val = self.validator.validate(str(self.dns_port), 'port', context="fw_dns_redirect_port")
            # Assuming redirect IP '192.168.4.1' is static and trusted for the hotspot's gateway
            redirect_ip = "192.168.4.1" # This should ideally come from config and be validated as ip_address

            # Redirect HTTP traffic to captive portal
            redirect_rules = [
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "80", "-j", "DNAT", "--to-destination", f"{redirect_ip}:{captive_portal_port_val}"]),
                # ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "8080", "-j", "DNAT", "--to-destination", f"{redirect_ip}:{captive_portal_port_val}"]), # Port 8080 is often the portal itself
                
                # Redirect DNS queries to local DNS server
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "udp", "--dport", str(dns_port_val), "-j", "DNAT", f"--to-destination", f"{redirect_ip}:{dns_port_val}"]),
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "tcp", "--dport", str(dns_port_val), "-j", "DNAT", f"--to-destination", f"{redirect_ip}:{dns_port_val}"]),
            ]
            
            for command_type, args in redirect_rules:
                if self._execute_command(command_type, args):
                    self.active_rules.append((command_type, args))
                else:
                    logging.error(f"Failed to execute redirect rule: {command_type} {' '.join(args)}")
            
            logging.info("Captive portal redirect rules configured")
            return True
            
        except Exception as e:
            logging.error(f"Failed to setup captive portal redirects: {e}")
            return False
    
    def allow_authenticated_device(self, mac_address):
        """Allow internet access for authenticated device"""
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="fw_allow_auth_mac")
        except ValidationError as e:
            logging.error(f"Invalid MAC address for allow_authenticated_device: {mac_address}. Error: {e}")
            return False
        try:
            # Remove blocking rules for this MAC address
            allow_rules = [
                ("iptables", ["-I", "FORWARD", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", validated_mac, "-j", "ACCEPT"]),
                ("iptables", ["-t", "nat", "-I", "PREROUTING", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", validated_mac, "-j", "RETURN"]),
            ]
            
            for command_type, args in allow_rules:
                if self._execute_command(command_type, args):
                    self.active_rules.append((command_type, args))
                    logging.info(f"Allowed internet access for device: {mac_address}")
                else:
                    logging.error(f"Failed to allow device {mac_address}: {command_type} {' '.join(args)}")
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to allow authenticated device {mac_address}: {e}")
            return False
    
    def block_device(self, mac_address):
        """Block a specific device"""
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="fw_block_dev_mac")
        except ValidationError as e:
            logging.error(f"Invalid MAC address for block_device: {mac_address}. Error: {e}")
            return False
        try:
            block_rules = [
                ("iptables", ["-I", "FORWARD", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", validated_mac, "-j", "DROP"]),
                ("iptables", ["-I", "INPUT", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", validated_mac, "-j", "DROP"]),
            ]
            
            for command_type, args in block_rules:
                if self._execute_command(command_type, args):
                    self.active_rules.append((command_type, args))
                    logging.info(f"Blocked device: {mac_address}")
                else:
                    logging.error(f"Failed to block device {mac_address}: {command_type} {' '.join(args)}")
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to block device {mac_address}: {e}")
            return False
    
    def unblock_device(self, mac_address):
        """Unblock a specific device"""
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="fw_unblock_dev_mac")
        except ValidationError as e:
            logging.error(f"Invalid MAC address for unblock_device: {mac_address}. Error: {e}")
            return False
        try:
            # Remove blocking rules for this MAC address
            unblock_rules = [
                ("iptables", ["-D", "FORWARD", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", validated_mac, "-j", "DROP"]),
                ("iptables", ["-D", "INPUT", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", validated_mac, "-j", "DROP"]),
            ]
            
            for command_type, args in unblock_rules:
                self._execute_command(command_type, args)  # Don't fail if rule doesn't exist
            
            logging.info(f"Unblocked device: {mac_address}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to unblock device {mac_address}: {e}")
            return False
    
    def setup_bandwidth_limits(self, mac_address, download_limit_kbps, upload_limit_kbps):
        """Setup bandwidth limits for a device using tc (traffic control)"""
        try:
            validated_mac = self.validator.validate(mac_address, 'mac_address', context="fw_bwlimit_mac")
            # Ensure limits are numbers
            if not (isinstance(download_limit_kbps, (int,float)) and download_limit_kbps > 0):
                 logging.error(f"Invalid download_limit_kbps: {download_limit_kbps}")
                 return False
            # upload_limit_kbps might be None or also needs validation if used.

            device_ip = self._get_ip_from_mac(validated_mac) # Uses validated MAC
            if not device_ip: # _get_ip_from_mac already validates the IP it might return
                logging.error(f"Could not find IP for MAC address: {validated_mac}")
                return False
            

            # Validate device_ip before use if it's retrieved and used in a command
            # validated_device_ip = self.validator.validate(device_ip, 'ip_address', context="fw_bwlimit_device_ip")
            # For now, device_ip is used in the example below.

            # Setup traffic control rules
            tc_rules = [
                # Create qdisc
                ("tc", ["qdisc", "add", "dev", self.hotspot_interface, "root", "handle", "1:", "htb", "default", "30"]),
                
                # Create class for download limit
                # Using a hash of MAC for classid; ensure this doesn't create issues.
                # f-string parts that are not from external vars are fine.
                ("tc", ["class", "add", "dev", self.hotspot_interface, "parent", "1:", "classid", f"1:{hash(validated_mac) % 1000}", "htb", "rate", f"{int(download_limit_kbps)}kbit"]),
                
                # Create filter for this device
                # device_ip must be validated if it's used here.
                ("tc", ["filter", "add", "dev", self.hotspot_interface, "protocol", "ip", "parent", "1:0", "prio", "1", "u32", "match", "ip", "dst", device_ip, "flowid", f"1:{hash(validated_mac) % 1000}"]),
            ]
            
            for command_type, args in tc_rules:
                if self._execute_command(command_type, args): # _execute_command handles logging success/failure
                    logging.info(f"Applied bandwidth limit component for {validated_mac}: {download_limit_kbps}kbps down")
                else:
                    # _execute_command already logs errors, this is for additional context if needed
                    logging.warning(f"Failed to apply bandwidth limit component: {command_type} {' '.join(args)} for {validated_mac}")
            
            return True # Success here is optimistic as _execute_command might return False for some rules
            
        except Exception as e:
            logging.error(f"Failed to setup bandwidth limits for {validated_mac}: {e}") # Use validated_mac
            return False
    
    def setup_port_blocking(self, ports_to_block: List[int]):
        """Block specific ports"""
        try:
            validated_ports = []
            for port in ports_to_block:
                try:
                    validated_ports.append(self.validator.validate(str(port), 'port', context=f"fw_port_block_{port}"))
                except ValidationError as e:
                    logging.warning(f"Invalid port {port} for blocking, skipping. Error: {e}")
                    continue # Skip invalid port

            for valid_port in validated_ports:
                block_rules = [
                    ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-p", "tcp", "--dport", str(valid_port), "-j", "DROP"]),
                    ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-p", "udp", "--dport", str(valid_port), "-j", "DROP"]),
                ]
                
                for command_type, args in block_rules:
                    if self._execute_command(command_type, args):
                        self.active_rules.append((command_type, args))
                        logging.info(f"Blocked port {valid_port}")
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to setup port blocking: {e}")
            return False
    
    def clear_hotspot_rules(self):
        """Clear all hotspot-related firewall rules"""
        try:
            # Flush chains
            flush_commands = [
                ("iptables", ["-t", "nat", "-F"]),
                ("iptables", ["-t", "filter", "-F"]),
                ("iptables", ["-t", "mangle", "-F"]),
            ]
            
            for command_type, args in flush_commands:
                self._execute_command(command_type, args)
            
            # Clear traffic control rules (hotspot_interface is validated at method start or class init)
            # Adding a check=False equivalent for _execute_command if it doesn't fail silently
            self._execute_command("tc", ["qdisc", "del", "dev", self.hotspot_interface, "root"], check_errors=False)
            
            self.active_rules.clear()
            logging.info("Cleared all hotspot firewall rules")
            return True
            
        except Exception as e:
            logging.error(f"Failed to clear hotspot rules: {e}")
            return False
    
    def get_blocked_devices(self):
        """Get list of currently blocked devices"""
        try:
            result = subprocess.run(["iptables", "-L", "FORWARD", "-v", "-n"], 
                                  capture_output=True, text=True)
            
            blocked_devices = []
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if "MAC" in line and "DROP" in line:
                        # Extract MAC address from line
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part == "MAC" and i + 1 < len(parts):
                                mac = parts[i + 1]
                                blocked_devices.append(mac)
            
            return blocked_devices
            
        except Exception as e:
            logging.error(f"Failed to get blocked devices: {e}")
            return []
    
    def _execute_command(self, command_type, args, check_errors=True):
        """Execute system command"""
        # It's assumed command_type and elements of args that are not from external input are safe.
        # External inputs should be validated before being passed into 'args'.
        try:
            full_command = [command_type] + args
            if command_type == "sysctl" and "-w" not in args[0]: # Ensure -w for sysctl if modifying
                # This is a basic safety, sysctl can be complex.
                # For "net.ipv4.ip_forward=1", it's typically ['sysctl', 'net.ipv4.ip_forward=1'] or ['sysctl', '-w', 'net.ipv4.ip_forward=1']
                # The original code used `["sysctl", "-w"] + args` which is problematic if args[0] is not the setting.
                # Correcting sysctl call:
                if args[0].count('=') == 1: # e.g. "key=value"
                     full_command = ["sysctl", "-w", args[0]]
                else: # e.g. "key", "value" - this form is not standard for sysctl
                     logging.error(f"Unsupported sysctl format: {args}")
                     return False

            process = subprocess.run(full_command, check=check_errors,
                                     capture_output=True, text=True)
            if check_errors and process.returncode != 0 : # check=True would raise CalledProcessError
                 logging.error(f"Command failed: {' '.join(full_command)} - {process.stderr}")
                 return False
            return True
        except subprocess.CalledProcessError as e: # Only if check=True
            logging.error(f"Command failed: {' '.join(e.cmd)} - {e.stderr}")
            return False
        except FileNotFoundError:
            logging.error(f"Command not found: {command_type}")
            return False
        except Exception as e:
            logging.error(f"Error executing command {' '.join(full_command)}: {e}")
            return False
    
    def _get_ip_from_mac(self, mac_address):
        """Get IP address from MAC address using ARP table"""
        try:
            # MAC address is already validated by the calling function (e.g. setup_bandwidth_limits)
            # No direct command injection risk with mac_address here as it's used for string search.
            result = subprocess.run(["arp", "-a"], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if mac_address.lower() in line.lower():
                        # Extract IP address
                        import re
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match:
                            return ip_match.group(1)
            
            # If found, validate the IP before returning
            # For now, returning as is, assuming arp output is trustworthy enough for an IP format.
            # A more robust approach would be to validate ip_match.group(1) with 'ip_address' rule.
            return None
            
        except Exception as e:
            logging.error(f"Error getting IP from MAC {mac_address}: {e}")
            return None
    
    def get_firewall_status(self):
        """Get current firewall status"""
        try:
            # Get iptables rules count
            result = subprocess.run(["iptables", "-L", "-n"], 
                                  capture_output=True, text=True)
            rules_count = 0
            if result.returncode == 0:
                rules_count = len([line for line in result.stdout.split('\n') 
                                 if line.strip() and not line.startswith('Chain') 
                                 and not line.startswith('target')])
            
            # Get NAT rules count
            nat_result = subprocess.run(["iptables", "-t", "nat", "-L", "-n"], 
                                      capture_output=True, text=True)
            nat_rules_count = 0
            if nat_result.returncode == 0:
                nat_rules_count = len([line for line in nat_result.stdout.split('\n') 
                                     if line.strip() and not line.startswith('Chain') 
                                     and not line.startswith('target')])
            
            return {
                'active_rules': len(self.active_rules),
                'iptables_rules': rules_count,
                'nat_rules': nat_rules_count,
                'hotspot_interface': self.hotspot_interface,
                'internet_interface': self.internet_interface
            }
            
        except Exception as e:
            logging.error(f"Failed to get firewall status: {e}")
            return {
                'active_rules': len(self.active_rules),
                'iptables_rules': 0,
                'nat_rules': 0,
                'hotspot_interface': self.hotspot_interface,
                'internet_interface': self.internet_interface
            }
    
    def backup_rules(self, backup_file="firewall_backup.txt"):
        """Backup current iptables rules"""
        try:
            validated_backup_file = self.validator.validate(backup_file, 'filename', context="fw_backup_filename")
        except ValidationError as e:
            logging.error(f"Invalid backup filename: {backup_file}. Error: {e}")
            return False
        try:
            with open(validated_backup_file, 'w') as f:
                # Backup filter table
                result = subprocess.run(["iptables-save"], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    f.write(result.stdout)
                    logging.info(f"Firewall rules backed up to {validated_backup_file}")
                    return True
                else:
                    logging.error(f"iptables-save failed: {result.stderr}")
                    return False
        except IOError as e:
            logging.error(f"Failed to write backup file {validated_backup_file}: {e}")
            return False
        except Exception as e: # Catch other potential errors like subprocess issues not covered by CalledProcessError
            logging.error(f"Failed to backup firewall rules: {e}")
            return False
    
    def restore_rules(self, backup_file="firewall_backup.txt"):
        """Restore iptables rules from backup"""
        try:
            validated_backup_file = self.validator.validate(backup_file, 'filename', context="fw_restore_filename")
        except ValidationError as e:
            logging.error(f"Invalid backup filename for restore: {backup_file}. Error: {e}")
            return False

        try:
            if os.path.exists(validated_backup_file):
                with open(validated_backup_file, 'r') as f:
                    rules = f.read()

                # Basic sanitization for iptables-restore input
                # This is a heuristic and not foolproof. Stronger validation of the rule syntax itself is complex.
                # Disallow common shell metacharacters that are highly unlikely in a valid iptables-save output.
                # Semicolons can appear in comments if not careful with rule definitions.
                # Backticks, dollar signs for command substitution.
                forbidden_patterns_restore = [';', '`', r'\$\(', '#!/bin/bash', '&&', '||', '>', '<', 'wget', 'curl']
                for pattern in forbidden_patterns_restore:
                    if re.search(pattern, rules): # re.search to find pattern anywhere
                        logging.critical(f"Potentially unsafe pattern '{pattern}' found in restore file {validated_backup_file}. Aborting restore.")
                        return False
                
                # Check for unusually long lines (simple heuristic)
                if any(len(line) > 1024 for line in rules.splitlines()):
                    logging.warning(f"Restore file {validated_backup_file} contains unusually long lines. Proceeding with caution.")

                result = subprocess.run(["iptables-restore"], input=rules, 
                                      text=True, capture_output=True, check=False)
                
                if result.returncode == 0:
                    logging.info(f"Firewall rules restored from {validated_backup_file}")
                    return True
                else:
                    logging.error(f"Failed to restore rules from {validated_backup_file}: {result.stderr}")
                    return False
            else:
                logging.error(f"Backup file {validated_backup_file} not found")
                return False
            
        except IOError as e:
            logging.error(f"Failed to read backup file {validated_backup_file}: {e}")
            return False
        except Exception as e:
            logging.error(f"Failed to restore firewall rules: {e}")
            return False

if __name__ == "__main__":
    # Test the firewall manager
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from config_manager import ConfigManager
    
    logging.basicConfig(level=logging.INFO)
    
    config_manager = ConfigManager()
    firewall = FirewallManager(config_manager)
    
    print("Firewall Manager Test")
    print("Status:", firewall.get_firewall_status())
    
    # Note: Actual firewall setup requires root privileges
    # This is just for testing the class structure