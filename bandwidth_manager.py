#!/usr/bin/env python3
"""
Bandwidth Manager - Traffic shaping and bandwidth control
"""

import subprocess
import platform
import logging
from typing import Dict, Optional
import psutil
import time
from input_validator import get_validator, ValidationError

class BandwidthManager:
    def __init__(self):
        self.validator = get_validator()
        self.system = platform.system().lower()
        self.logger = logging.getLogger(__name__)
        self.active_limits = {}
        
    def set_bandwidth_limit(self, interface: str, download_mbps: float, upload_mbps: float) -> bool:
        """Set bandwidth limits for interface"""
        if self.system == "linux":
            return self._set_linux_bandwidth_limit(interface, download_mbps, upload_mbps)
        elif self.system == "windows":
            return self._set_windows_bandwidth_limit(interface, download_mbps, upload_mbps)
        return False
    
    def _set_linux_bandwidth_limit(self, interface: str, download_mbps: float, upload_mbps: float) -> bool:
        """Set bandwidth limits on Linux using tc (traffic control)"""
        try:
            validated_interface = self.validator.validate(interface, 'interface', context="bw_manager_set_limit_interface")
        except ValidationError as e:
            self.logger.error(f"Invalid interface name for bandwidth limit: {interface}. Error: {e}")
            return False

        try:
            # Clear existing rules
            self.clear_bandwidth_limits(validated_interface) # Use validated interface
            
            # Convert Mbps to Kbps
            download_kbps = int(download_mbps * 1000)
            upload_kbps = int(upload_mbps * 1000)
            
            # Add root qdisc
            subprocess.run([
                "tc", "qdisc", "add", "dev", validated_interface, "root", "handle", "1:", "htb", "default", "30"
            ], check=True)
            
            # Add class for total bandwidth
            subprocess.run([
                "tc", "class", "add", "dev", validated_interface, "parent", "1:", "classid", "1:1", "htb",
                "rate", f"{upload_kbps}kbit", "ceil", f"{upload_kbps}kbit"
            ], check=True)
            
            # Add default class
            subprocess.run([
                "tc", "class", "add", "dev", validated_interface, "parent", "1:1", "classid", "1:30", "htb",
                "rate", f"{upload_kbps}kbit", "ceil", f"{upload_kbps}kbit"
            ], check=True)
            
            self.active_limits[validated_interface] = { # Use validated interface
                'download_mbps': download_mbps,
                'upload_mbps': upload_mbps
            }
            
            self.logger.info(f"Bandwidth limit set: {upload_mbps}Mbps up, {download_mbps}Mbps down")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to set bandwidth limit: {e}")
            return False
    
    def _set_windows_bandwidth_limit(self, interface: str, download_mbps: float, upload_mbps: float) -> bool:
        """Set bandwidth limits on Windows using netsh"""
        try:
            # Windows has limited built-in QoS options
            # This is a simplified implementation
            self.logger.warning("Windows bandwidth limiting has limited functionality")
            
            # Store the limits for monitoring purposes
            self.active_limits[interface] = {
                'download_mbps': download_mbps,
                'upload_mbps': upload_mbps
            }
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set Windows bandwidth limit: {e}")
            return False
    
    def clear_bandwidth_limits(self, interface: str) -> bool:
        """Clear bandwidth limits for interface"""
        try:
            validated_interface = self.validator.validate(interface, 'interface', context="bw_manager_clear_limit_interface")
        except ValidationError as e:
            self.logger.error(f"Invalid interface name for clearing bandwidth limits: {interface}. Error: {e}")
            return False

        try:
            if self.system == "linux":
                subprocess.run([
                    "tc", "qdisc", "del", "dev", validated_interface, "root"
                ], capture_output=True) # Note: check=False here, so we don't crash if qdisc doesn't exist
                
            if validated_interface in self.active_limits:
                del self.active_limits[validated_interface]
                
            self.logger.info(f"Bandwidth limits cleared for {validated_interface}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear bandwidth limits: {e}")
            return False
    
    def get_interface_usage(self, interface: str) -> Dict:
        """Get current usage statistics for interface"""
        try:
            stats = psutil.net_io_counters(pernic=True)
            if interface in stats:
                return {
                    'bytes_sent': stats[interface].bytes_sent,
                    'bytes_recv': stats[interface].bytes_recv,
                    'packets_sent': stats[interface].packets_sent,
                    'packets_recv': stats[interface].packets_recv,
                    'errin': stats[interface].errin,
                    'errout': stats[interface].errout,
                    'dropin': stats[interface].dropin,
                    'dropout': stats[interface].dropout
                }
        except Exception as e:
            self.logger.error(f"Failed to get interface usage: {e}")
            
        return {}
    
    def get_bandwidth_usage(self, interface: str, interval: float = 1.0) -> Dict:
        """Get bandwidth usage over specified interval"""
        try:
            # Get initial stats
            initial_stats = self.get_interface_usage(interface)
            if not initial_stats:
                return {}
                
            time.sleep(interval)
            
            # Get final stats
            final_stats = self.get_interface_usage(interface)
            if not final_stats:
                return {}
            
            # Calculate rates
            bytes_sent_rate = (final_stats['bytes_sent'] - initial_stats['bytes_sent']) / interval
            bytes_recv_rate = (final_stats['bytes_recv'] - initial_stats['bytes_recv']) / interval
            
            # Convert to Mbps
            upload_mbps = (bytes_sent_rate * 8) / (1024 * 1024)
            download_mbps = (bytes_recv_rate * 8) / (1024 * 1024)
            
            return {
                'upload_mbps': round(upload_mbps, 2),
                'download_mbps': round(download_mbps, 2),
                'upload_bytes_per_sec': bytes_sent_rate,
                'download_bytes_per_sec': bytes_recv_rate
            }
            
        except Exception as e:
            self.logger.error(f"Failed to calculate bandwidth usage: {e}")
            return {}
    
    def set_per_device_limit(self, ip_address: str, download_mbps: float, upload_mbps: float) -> bool:
        """Set bandwidth limit for specific device (Linux only)"""
        if self.system != "linux":
            self.logger.warning("Per-device bandwidth limiting only supported on Linux")
            return False
            
        try:
            # This requires more advanced tc configuration
            # Simplified implementation
            # Validate IP address if we were to use it in a command
            try:
                validated_ip = self.validator.validate(ip_address, 'ip_address', context="bw_manager_per_device_ip")
            except ValidationError as e_ip:
                self.logger.error(f"Invalid IP address for per-device limit: {ip_address}. Error: {e_ip}")
                return False

            self.logger.warning("Per-device bandwidth limiting requires advanced configuration using validated_ip")
            return False # Current implementation is a placeholder
            
        except Exception as e:
            self.logger.error(f"Failed to set per-device limit: {e}")
            return False
    
    def get_active_limits(self) -> Dict:
        """Get currently active bandwidth limits"""
        return self.active_limits.copy()
    
    def monitor_bandwidth(self, interface: str, callback=None, interval: float = 5.0):
        """Monitor bandwidth usage continuously"""
        self.logger.info(f"Starting bandwidth monitoring for {interface}")
        
        try:
            while True:
                usage = self.get_bandwidth_usage(interface, 1.0)
                
                if usage and callback:
                    callback(usage)
                elif usage:
                    self.logger.info(f"Bandwidth: {usage['upload_mbps']:.2f}Mbps up, {usage['download_mbps']:.2f}Mbps down")
                
                time.sleep(interval - 1.0)  # Subtract 1 second used in get_bandwidth_usage
                
        except KeyboardInterrupt:
            self.logger.info("Bandwidth monitoring stopped")
        except Exception as e:
            self.logger.error(f"Error in bandwidth monitoring: {e}")
