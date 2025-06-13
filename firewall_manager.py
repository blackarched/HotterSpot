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

class FirewallManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
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
        self.hotspot_interface = hotspot_interface
        self.internet_interface = internet_interface
        
        try:
            # Clear existing rules
            self.clear_hotspot_rules()
            
            # Setup basic rules
            rules = [
                # Enable IP forwarding
                ("sysctl", ["net.ipv4.ip_forward=1"]),
                
                # NAT rules for internet sharing
                ("iptables", ["-t", "nat", "-A", "POSTROUTING", "-o", internet_interface, "-j", "MASQUERADE"]),
                ("iptables", ["-A", "FORWARD", "-i", internet_interface, "-o", hotspot_interface, "-m", "state", "--state", "RELATED,ESTABLISHED", "-j", "ACCEPT"]),
                ("iptables", ["-A", "FORWARD", "-i", hotspot_interface, "-o", internet_interface, "-j", "ACCEPT"]),
                
                # Allow DNS traffic
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-p", "udp", "--dport", str(self.dns_port), "-j", "ACCEPT"]),
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-p", "tcp", "--dport", str(self.dns_port), "-j", "ACCEPT"]),
                
                # Allow DHCP traffic
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-p", "udp", "--dport", "67", "-j", "ACCEPT"]),
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-p", "udp", "--dport", "68", "-j", "ACCEPT"]),
                
                # Allow captive portal traffic
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-p", "tcp", "--dport", str(self.captive_portal_port), "-j", "ACCEPT"]),
                
                # Allow SSH (optional, for management)
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-p", "tcp", "--dport", "22", "-j", "ACCEPT"]),
                
                # Block direct internet access until authenticated (captive portal)
                ("iptables", ["-A", "FORWARD", "-i", hotspot_interface, "-p", "tcp", "--dport", "80", "-j", "REJECT"]),
                ("iptables", ["-A", "FORWARD", "-i", hotspot_interface, "-p", "tcp", "--dport", "443", "-j", "REJECT"]),
                
                # Drop other traffic by default
                ("iptables", ["-A", "INPUT", "-i", hotspot_interface, "-j", "DROP"]),
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
        try:
            # Redirect HTTP traffic to captive portal
            redirect_rules = [
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "80", "-j", "DNAT", "--to-destination", f"192.168.4.1:{self.captive_portal_port}"]),
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "8080", "-j", "DNAT", "--to-destination", f"192.168.4.1:{self.captive_portal_port}"]),
                
                # Redirect DNS queries to local DNS server
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "udp", "--dport", "53", "-j", "DNAT", "--to-destination", "192.168.4.1:53"]),
                ("iptables", ["-t", "nat", "-A", "PREROUTING", "-i", self.hotspot_interface, "-p", "tcp", "--dport", "53", "-j", "DNAT", "--to-destination", "192.168.4.1:53"]),
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
            # Remove blocking rules for this MAC address
            allow_rules = [
                ("iptables", ["-I", "FORWARD", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", mac_address, "-j", "ACCEPT"]),
                ("iptables", ["-t", "nat", "-I", "PREROUTING", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", mac_address, "-j", "RETURN"]),
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
            block_rules = [
                ("iptables", ["-I", "FORWARD", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", mac_address, "-j", "DROP"]),
                ("iptables", ["-I", "INPUT", "1", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", mac_address, "-j", "DROP"]),
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
            # Remove blocking rules for this MAC address
            unblock_rules = [
                ("iptables", ["-D", "FORWARD", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", mac_address, "-j", "DROP"]),
                ("iptables", ["-D", "INPUT", "-i", self.hotspot_interface, "-m", "mac", "--mac-source", mac_address, "-j", "DROP"]),
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
            device_ip = self._get_ip_from_mac(mac_address)
            if not device_ip:
                logging.error(f"Could not find IP for MAC address: {mac_address}")
                return False
            
            # Setup traffic control rules
            tc_rules = [
                # Create qdisc
                ("tc", ["qdisc", "add", "dev", self.hotspot_interface, "root", "handle", "1:", "htb", "default", "30"]),
                
                # Create class for download limit
                ("tc", ["class", "add", "dev", self.hotspot_interface, "parent", "1:", "classid", f"1:{hash(mac_address) % 1000}", "htb", "rate", f"{download_limit_kbps}kbit"]),
                
                # Create filter for this device
                ("tc", ["filter", "add", "dev", self.hotspot_interface, "protocol", "ip", "parent", "1:0", "prio", "1", "u32", "match", "ip", "dst", device_ip, "flowid", f"1:{hash(mac_address) % 1000}"]),
            ]
            
            for command_type, args in tc_rules:
                if self._execute_command(command_type, args):
                    logging.info(f"Applied bandwidth limit for {mac_address}: {download_limit_kbps}kbps down")
                else:
                    logging.warning(f"Failed to apply bandwidth limit: {command_type} {' '.join(args)}")
            
            return True
            
        except Exception as e:
            logging.error(f"Failed to setup bandwidth limits for {mac_address}: {e}")
            return False
    
    def setup_port_blocking(self, ports_to_block):
        """Block specific ports"""
        try:
            for port in ports_to_block:
                block_rules = [
                    ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-p", "tcp", "--dport", str(port), "-j", "DROP"]),
                    ("iptables", ["-A", "FORWARD", "-i", self.hotspot_interface, "-p", "udp", "--dport", str(port), "-j", "DROP"]),
                ]
                
                for command_type, args in block_rules:
                    if self._execute_command(command_type, args):
                        self.active_rules.append((command_type, args))
                        logging.info(f"Blocked port {port}")
            
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
            
            # Clear traffic control rules
            self._execute_command("tc", ["qdisc", "del", "dev", self.hotspot_interface, "root"])
            
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
    
    def _execute_command(self, command_type, args):
        """Execute system command"""
        try:
            if command_type == "sysctl":
                # Special handling for sysctl
                subprocess.run(["sysctl", "-w"] + args, check=True, 
                             capture_output=True, text=True)
            else:
                subprocess.run([command_type] + args, check=True, 
                             capture_output=True, text=True)
            return True
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {command_type} {' '.join(args)} - {e.stderr}")
            return False
        except Exception as e:
            logging.error(f"Error executing command: {e}")
            return False
    
    def _get_ip_from_mac(self, mac_address):
        """Get IP address from MAC address using ARP table"""
        try:
            result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if mac_address.lower() in line.lower():
                        # Extract IP address
                        import re
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match:
                            return ip_match.group(1)
            
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
            with open(backup_file, 'w') as f:
                # Backup filter table
                result = subprocess.run(["iptables-save"], capture_output=True, text=True)
                if result.returncode == 0:
                    f.write(result.stdout)
                    logging.info(f"Firewall rules backed up to {backup_file}")
                    return True
            
            return False
            
        except Exception as e:
            logging.error(f"Failed to backup firewall rules: {e}")
            return False
    
    def restore_rules(self, backup_file="firewall_backup.txt"):
        """Restore iptables rules from backup"""
        try:
            if os.path.exists(backup_file):
                with open(backup_file, 'r') as f:
                    rules = f.read()
                
                result = subprocess.run(["iptables-restore"], input=rules, 
                                      text=True, capture_output=True)
                
                if result.returncode == 0:
                    logging.info(f"Firewall rules restored from {backup_file}")
                    return True
                else:
                    logging.error(f"Failed to restore rules: {result.stderr}")
                    return False
            else:
                logging.error(f"Backup file {backup_file} not found")
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