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
from service_manager import ProcessManager # Added
from config_manager import ConfigManager # Added
import os # Added

class HotspotManager:
    def __init__(self):
        self.validator = get_validator()
        self.config_manager = ConfigManager()
        self.process_manager = ProcessManager()
        self.nmcli_connection_name = "HotterSpotAP" # Standardized name
        self.dnsmasq_process_name = "hotspot_dnsmasq"
        self.dnsmasq_conf_path = "/tmp/hotterspot_dnsmasq.conf"
        self.dnsmasq_lease_path = "/tmp/hotterspot.leases" # Added for dnsmasq lease file
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
                self.current_ssid = ssid
                self.current_password = password
                self.logger.info(f"Hotspot '{ssid}' (nmcli) created successfully on interface {self.interface}")

                # Now, configure and start dnsmasq
                # Update ConfigManager's current config to reflect active hotspot settings
                self.config_manager.config['interface'] = self.interface
                self.config_manager.config['ssid'] = ssid
                # hotspot_ip might need to be dynamically determined or be reliably static from config
                # For now, we assume it's correctly set in config_manager.config by its load_main_config

                dnsmasq_conf_str = self.config_manager.generate_dnsmasq_config()
                try:
                    with open(self.dnsmasq_conf_path, 'w') as f:
                        f.write(dnsmasq_conf_str)
                    self.logger.info(f"dnsmasq config written to {self.dnsmasq_conf_path}")
                except IOError as e:
                    self.logger.error(f"Failed to write dnsmasq config file {self.dnsmasq_conf_path}: {e}")
                    self._internal_stop_nmcli_hotspot() # Attempt to stop nmcli part
                    return False

                # Define dnsmasq command
                # Ensure user 'root' or 'dnsmasq' has permissions for leasefile, pidfile etc.
                # Default leasefile for dnsmasq is often in /var/lib/misc/dnsmasq.leases
                dnsmasq_cmd = [
                    'dnsmasq',
                    '-C', self.dnsmasq_conf_path,
                    '-k',  # Keep in foreground for ProcessManager
                    '--user=root', # Or 'dnsmasq' if that user exists and has perms for lease file /var/lib/dnsmasq/dnsmasq.leases
                    '--group=root', # Or 'dnsmasq'
                    '--log-dhcp', # Useful for debugging
                    # '--log-queries' # Very verbose
                    # '--no-resolv' # If only using specified 'server=' lines in conf
                    # '--no-hosts'  # If not using /etc/hosts
                ]

                dnsmasq_pid = self.process_manager.start_process(self.dnsmasq_process_name, dnsmasq_cmd)
                if not dnsmasq_pid:
                    self.logger.error("Failed to start dnsmasq process.")
                    if os.path.exists(self.dnsmasq_conf_path):
                        try:
                            os.remove(self.dnsmasq_conf_path)
                        except OSError as e_rm:
                            self.logger.error(f"Error removing temp dnsmasq conf after start failure: {e_rm}")
                    self._internal_stop_nmcli_hotspot() # Attempt to stop nmcli part
                    return False

                self.logger.info(f"dnsmasq started with PID {dnsmasq_pid} using config {self.dnsmasq_conf_path}")
                return True # Both nmcli hotspot and dnsmasq started
            else:
                self.logger.error(f"Failed to create nmcli hotspot: {result.stderr}")
                return False
        except subprocess.CalledProcessError as e: # Should be caught by check=False and result.returncode check
            self.logger.error(f"Error creating Linux hotspot (subprocess error): {e}")
            return False
        except Exception as e_gen: # Catch any other general exception
            self.logger.error(f"A general error occurred during Linux hotspot creation: {e_gen}")
            return False

    def _internal_stop_nmcli_hotspot(self):
        """Internal helper to stop nmcli hotspot part, without affecting dnsmasq state directly here."""
        self.logger.info("Attempting to stop nmcli hotspot part...")
        subprocess.run(["nmcli", "connection", "down", "HotspotTool"], capture_output=True, text=True)
        subprocess.run(["nmcli", "connection", "delete", "HotspotTool"], capture_output=True, text=True)
        self.logger.info("nmcli hotspot part stop commands issued.")

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
        """Stop the active hotspot and associated services like dnsmasq"""
        stopped_nmcli = False
        try:
            if self.system == "linux":
                self.logger.info("Stopping Linux hotspot (nmcli and dnsmasq)...")
                # Stop dnsmasq first
                if self.process_manager.stop_process(self.dnsmasq_process_name):
                    self.logger.info("dnsmasq process stopped successfully.")
                else:
                    self.logger.warning(f"Could not stop dnsmasq process '{self.dnsmasq_process_name}' or it was not running.")

                # Clean up dnsmasq config and lease files
                for f_path in [self.dnsmasq_conf_path, self.dnsmasq_lease_path]: # Added lease_path
                    if os.path.exists(f_path):
                        try:
                            os.remove(f_path)
                            self.logger.info(f"Removed dnsmasq file: {f_path}")
                        except OSError as e:
                            self.logger.error(f"Failed to remove dnsmasq file {f_path}: {e}")

                # Stop nmcli hotspot
                nmcli_down_res = subprocess.run(
                    ["nmcli", "connection", "down", self.nmcli_connection_name], # Use standardized name
                    capture_output=True, text=True, check=False
                )
                nmcli_delete_res = subprocess.run(
                    ["nmcli", "connection", "delete", self.nmcli_connection_name], # Use standardized name
                    capture_output=True, text=True, check=False
                )
                # Log results but don't necessarily fail the whole stop operation if nmcli commands have issues
                if nmcli_down_res.returncode == 0:
                    self.logger.info(f"nmcli connection '{self.nmcli_connection_name}' brought down.")
                else:
                    self.logger.warning(f"nmcli connection down '{self.nmcli_connection_name}' failed (it might be already down): {nmcli_down_res.stderr}")
                
                if nmcli_delete_res.returncode == 0:
                    self.logger.info(f"nmcli connection '{self.nmcli_connection_name}' deleted.")
                else:
                    self.logger.warning(f"nmcli connection delete '{self.nmcli_connection_name}' failed (it might be already deleted): {nmcli_delete_res.stderr}")
                stopped_nmcli = True # Assume attempted, even if errors, for state reset

            elif self.system == "windows":
                self.logger.info("Stopping Windows hotspot...")
                result = subprocess.run(
                    ["netsh", "wlan", "stop", "hostednetwork"],
                    capture_output=True, text=True, check=False
                )
                if result.returncode == 0:
                    stopped_nmcli = True # Representing generic hotspot part stopped
                else:
                    self.logger.error(f"Failed to stop Windows hostednetwork: {result.stderr}")

            # Reset state if underlying hotspot mechanism stopped successfully or was already inactive
            self.is_active = False
            self.current_ssid = None
            self.current_password = None
            self.interface = None # Reset interface
            self.logger.info("Hotspot stopped and state reset.")
            return True # Return true to indicate attempt was made, even if parts failed silently
            
        except Exception as e: # General exception catch
            self.logger.error(f"Error during hotspot stop procedure: {e}")
            # Attempt to reset state anyway
            self.is_active = False # Ensure is_active is false on any exception during stop
            self.current_ssid = None
            self.current_password = None
            self.interface = None
            return False
    
    def get_hotspot_status(self) -> Dict:
        """Get current hotspot status, performing a real-time check for Linux."""
        if self.system == "linux":
            is_currently_active = False
            # active_ssid = None # SSID from nmcli can be complex if not self.nmcli_connection_name
            # active_interface = None

            # Check if dnsmasq process is running (optional, but good indicator)
            dnsmasq_running = self.process_manager.get_process_status(self.dnsmasq_process_name).get('status') == 'running'
            if not dnsmasq_running and self.is_active: # If we thought we were active but dnsmasq isn't
                 self.logger.warning("get_hotspot_status: dnsmasq not running but hotspot was thought to be active.")
                 # This might indicate a problem, but nmcli is the primary source of truth for the AP itself.

            if self.interface : # Only check if we think an interface was set for the hotspot
                try:
                    # Use -t for terse, -m multiline for easier parsing if needed, but terse is fine for specific fields
                    cmd = ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE,STATE", "connection", "show", "--active"]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

                    for line in result.stdout.strip().split('\n'):
                        parts = line.split(':')
                        if len(parts) >= 4: # NAME, TYPE, DEVICE, STATE
                            name, conn_type, device, state = parts[0], parts[1], parts[2], parts[3]
                            # Check if the connection name and device match our hotspot, and if it's active
                            if name == self.nmcli_connection_name and device == self.interface and state.lower() == 'activated':
                                is_currently_active = True
                                break
                except subprocess.CalledProcessError as e:
                    self.logger.error(f"Failed to get real-time nmcli status (CalledProcessError): {e.stderr}")
                except FileNotFoundError:
                    self.logger.error("nmcli command not found for status check.")
                except Exception as e:
                    self.logger.error(f"An error occurred while checking nmcli status: {e}")

            # Update internal state based on real-time check
            if not is_currently_active and self.is_active:
                self.logger.info(f"Hotspot connection '{self.nmcli_connection_name}' on device '{self.interface}' no longer active or found. Updating status.")
                # If nmcli connection is gone, dnsmasq should also be stopped if it wasn't already.
                if dnsmasq_running:
                     self.logger.warning("nmcli hotspot part is inactive, but dnsmasq seems to be running. Consider stopping dnsmasq.")
                     # self.process_manager.stop_process(self.dnsmasq_process_name) # Optionally stop it here
                self.current_ssid = None # Clear stored SSID if hotspot is confirmed down
                self.interface = None    # Clear stored interface

            self.is_active = is_currently_active

        # For Windows or if Linux check fails and relies on stored state:
        return {
            'active': self.is_active,
            'ssid': self.current_ssid,
            'password': "********" if self.current_password else None, # Don't expose password directly
            'interface': self.interface,
            'connected_devices': len(self.get_connected_devices()) if self.is_active else 0
        }
    
    def get_connected_devices(self) -> List[Dict]:
        """Get list of connected devices"""
        devices = []
        if not self.is_active: # Only try to get devices if hotspot is marked active
            return devices
            
        if self.system == "linux":
            devices = self._get_linux_connected_devices_from_lease()
            if not devices: # Fallback or supplement with ARP if lease file is empty/unavailable
                self.logger.debug("Lease file empty or unreadable, trying ARP as fallback for connected devices.")
                devices = self._get_linux_connected_devices_arp()
        elif self.system == "windows":
            devices = self._get_windows_connected_devices()
            
        return devices

    def _parse_dnsmasq_lease_file(self) -> List[Dict]:
        devices = []
        try:
            with open(self.dnsmasq_lease_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        # Format: expiry_timestamp mac_address ip_address hostname client_id
                        # Example: 1700000000 00:11:22:33:44:55 192.168.4.132 MyDevice *
                        # Some dnsmasq versions might have lease time instead of expiry.
                        # Assuming expiry_timestamp for now.
                        try:
                            expiry_ts = int(parts[0])
                            mac, ip, hostname_str = parts[1], parts[2], parts[3]
                            hostname = hostname_str if hostname_str != '*' and hostname_str != '-' else 'Unknown'

                            # Optional: Check if lease is current
                            # current_time = int(time.time())
                            # if expiry_ts < current_time and expiry_ts != 0: # 0 can mean infinite/static
                            #    continue

                            devices.append({
                                'ip': ip,
                                'mac': mac.lower(), # Standardize MAC to lowercase
                                'hostname': hostname,
                                'connected_time': datetime.fromtimestamp(expiry_ts).isoformat() if expiry_ts != 0 else "static/infinite"
                            })
                        except ValueError: # Handle if timestamp is not an int
                            self.logger.warning(f"Could not parse lease line: {line.strip()}")
                            continue
        except FileNotFoundError:
            self.logger.info(f"dnsmasq lease file not found at {self.dnsmasq_lease_path}. No devices from leases.")
        except Exception as e:
            self.logger.error(f"Error parsing dnsmasq lease file {self.dnsmasq_lease_path}: {e}")
        return devices

    def _get_linux_connected_devices_from_lease(self) -> List[Dict]:
        """Get connected devices on Linux from dnsmasq lease file."""
        return self._parse_dnsmasq_lease_file()

    def _get_linux_connected_devices_arp(self) -> List[Dict]:
        """Get connected devices on Linux using ARP table as a fallback."""
        devices = []
        if not self.interface: # ARP needs an interface to be meaningful for the hotspot
            self.logger.debug("ARP check skipped: Hotspot interface not set.")
            return devices
        try:
            result = subprocess.run(["arp", "-a", "-i", self.interface], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.strip(): # Ensure line is not empty
                        match = re.search(r'\(([\d.]+)\) at ([a-fA-F0-9:]+)', line)
                        if match:
                            ip = match.group(1)
                            mac = match.group(2).lower() # Standardize MAC
                            
                            # Check if IP is likely part of the hotspot's subnet
                            # This is a heuristic; requires hotspot_ip to be set in config_manager
                            hotspot_base_ip = self.config_manager.config.get('hotspot_ip', '').rsplit('.', 1)[0]
                            if hotspot_base_ip and ip.startswith(hotspot_base_ip + '.'):
                                devices.append({
                                    'ip': ip,
                                    'mac': mac,
                                    'hostname': self._get_hostname(ip),
                                    'connected_time': "N/A (from ARP)"
                                })
            else:
                self.logger.warning(f"arp -a -i {self.interface} command failed or produced no output. stderr: {result.stderr}")
        except FileNotFoundError:
            self.logger.error("arp command not found. Cannot list connected devices via ARP.")
        except Exception as e:
            self.logger.error(f"Error getting connected devices via ARP: {e}")
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
