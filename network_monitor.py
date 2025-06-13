#!/usr/bin/env python3
"""
Network Monitor Script for Hotspot Tool
Monitors connected devices, data usage, and network performance
"""

import subprocess
import json
import time
import threading
from datetime import datetime
import psutil
import re

class NetworkMonitor:
    def __init__(self):
        self.connected_devices = {}
        self.data_usage = {}
        self.monitoring = False
        self.monitor_thread = None
        
    def get_connected_devices_linux(self):
        """Get list of connected devices on Linux"""
        devices = []
        try:
            # Get DHCP leases
            result = subprocess.run(['cat', '/var/lib/dhcp/dhcpd.leases'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                leases = self.parse_dhcp_leases(result.stdout)
                devices.extend(leases)
            
            # Get ARP table as backup
            arp_result = subprocess.run(['arp', '-a'], capture_output=True, text=True)
            if arp_result.returncode == 0:
                arp_devices = self.parse_arp_table(arp_result.stdout)
                devices.extend(arp_devices)
                
        except Exception as e:
            print(f"Error getting connected devices: {e}")
            
        return self.deduplicate_devices(devices)
    
    def get_connected_devices_windows(self):
        """Get list of connected devices on Windows"""
        devices = []
        try:
            # Get hosted network status
            result = subprocess.run(['netsh', 'wlan', 'show', 'hostednetwork'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                devices = self.parse_windows_clients(result.stdout)
                
        except Exception as e:
            print(f"Error getting connected devices: {e}")
            
        return devices
    
    def parse_dhcp_leases(self, leases_content):
        """Parse DHCP leases file"""
        devices = []
        lease_blocks = leases_content.split('lease ')
        
        for block in lease_blocks[1:]:  # Skip first empty split
            try:
                ip_match = re.search(r'^(\d+\.\d+\.\d+\.\d+)', block)
                mac_match = re.search(r'hardware ethernet ([a-fA-F0-9:]{17})', block)
                hostname_match = re.search(r'client-hostname "([^"]+)"', block)
                
                if ip_match and mac_match:
                    device = {
                        'ip': ip_match.group(1),
                        'mac': mac_match.group(1).upper(),
                        'hostname': hostname_match.group(1) if hostname_match else 'Unknown',
                        'connected_time': datetime.now().isoformat()
                    }
                    devices.append(device)
            except Exception:
                continue
                
        return devices
    
    def parse_arp_table(self, arp_output):
        """Parse ARP table output"""
        devices = []
        lines = arp_output.strip().split('\n')
        
        for line in lines:
            # Match format: hostname (ip) at mac [ether] on interface
            match = re.search(r'\((\d+\.\d+\.\d+\.\d+)\) at ([a-fA-F0-9:]{17})', line)
            if match:
                device = {
                    'ip': match.group(1),
                    'mac': match.group(2).upper(),
                    'hostname': 'Unknown',
                    'connected_time': datetime.now().isoformat()
                }
                devices.append(device)
                
        return devices
    
    def parse_windows_clients(self, netsh_output):
        """Parse Windows netsh hosted network output"""
        devices = []
        lines = netsh_output.split('\n')
        
        for line in lines:
            if 'Client' in line:
                # Extract MAC address from client line
                mac_match = re.search(r'([a-fA-F0-9]{2}-[a-fA-F0-9]{2}-[a-fA-F0-9]{2}-[a-fA-F0-9]{2}-[a-fA-F0-9]{2}-[a-fA-F0-9]{2})', line)
                if mac_match:
                    mac = mac_match.group(1).replace('-', ':')
                    device = {
                        'ip': 'Unknown',
                        'mac': mac,
                        'hostname': 'Unknown',
                        'connected_time': datetime.now().isoformat()
                    }
                    devices.append(device)
                    
        return devices
    
    def deduplicate_devices(self, devices):
        """Remove duplicate devices based on MAC address"""
        seen_macs = set()
        unique_devices = []
        
        for device in devices:
            if device['mac'] not in seen_macs:
                seen_macs.add(device['mac'])
                unique_devices.append(device)
                
        return unique_devices
    
    def get_network_interface_stats(self, interface=None):
        """Get network interface statistics"""
        stats = psutil.net_io_counters(pernic=True)
        
        if interface and interface in stats:
            return {
                'bytes_sent': stats[interface].bytes_sent,
                'bytes_recv': stats[interface].bytes_recv,
                'packets_sent': stats[interface].packets_sent,
                'packets_recv': stats[interface].packets_recv
            }
        else:
            # Return combined stats for all interfaces
            total = psutil.net_io_counters()
            return {
                'bytes_sent': total.bytes_sent,
                'bytes_recv': total.bytes_recv,
                'packets_sent': total.packets_sent,
                'packets_recv': total.packets_recv
            }
    
    def monitor_data_usage(self):
        """Monitor data usage in background thread"""
        previous_stats = self.get_network_interface_stats()
        
        while self.monitoring:
            time.sleep(5)  # Update every 5 seconds
            
            current_stats = self.get_network_interface_stats()
            
            # Calculate difference
            usage = {
                'bytes_sent_delta': current_stats['bytes_sent'] - previous_stats['bytes_sent'],
                'bytes_recv_delta': current_stats['bytes_recv'] - previous_stats['bytes_recv'],
                'timestamp': datetime.now().isoformat(),
                'total_sent': current_stats['bytes_sent'],
                'total_recv': current_stats['bytes_recv']
            }
            
            self.data_usage[datetime.now().isoformat()] = usage
            previous_stats = current_stats
    
    def start_monitoring(self):
        """Start network monitoring"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_data_usage)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            print("Network monitoring started")
    
    def stop_monitoring(self):
        """Stop network monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        print("Network monitoring stopped")
    
    def get_current_status(self):
        """Get current network status"""
        import platform
        
        if platform.system() == 'Linux':
            devices = self.get_connected_devices_linux()
        else:
            devices = self.get_connected_devices_windows()
        
        stats = self.get_network_interface_stats()
        
        return {
            'connected_devices': devices,
            'device_count': len(devices),
            'network_stats': stats,
            'monitoring_active': self.monitoring,
            'timestamp': datetime.now().isoformat()
        }
    
    def format_bytes(self, bytes_count):
        """Format bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.2f} PB"
    
    def save_status_to_file(self, filename='network_status.json'):
        """Save current status to JSON file"""
        status = self.get_current_status()
        try:
            with open(filename, 'w') as f:
                json.dump(status, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving status: {e}")
            return False

def main():
    """Main function for testing"""
    monitor = NetworkMonitor()
    
    # Start monitoring
    monitor.start_monitoring()
    
    try:
        while True:
            status = monitor.get_current_status()
            print(f"\n--- Network Status at {status['timestamp']} ---")
            print(f"Connected Devices: {status['device_count']}")
            
            for device in status['connected_devices']:
                print(f"  - {device['hostname']} ({device['ip']}) - {device['mac']}")
            
            stats = status['network_stats']
            print(f"Total Data Sent: {monitor.format_bytes(stats['bytes_sent'])}")
            print(f"Total Data Received: {monitor.format_bytes(stats['bytes_recv'])}")
            
            # Save to file
            monitor.save_status_to_file()
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\nStopping monitor...")
        monitor.stop_monitoring()

if __name__ == "__main__":
    main()
