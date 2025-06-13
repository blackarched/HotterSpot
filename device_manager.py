#!/usr/bin/env python3
"""
Device Manager Script for Hotspot Tool
Manages connected devices, blocking/unblocking, and access control
"""

import subprocess
import json
import os
import time
from datetime import datetime
import platform

class DeviceManager:
    def __init__(self, config_dir='hotspot_config'):
        self.config_dir = config_dir
        self.blocked_devices_file = os.path.join(config_dir, 'blocked_devices.json')
        self.allowed_devices_file = os.path.join(config_dir, 'allowed_devices.json')
        self.device_limits_file = os.path.join(config_dir, 'device_limits.json')
        
        self.blocked_devices = self.load_blocked_devices()
        self.allowed_devices = self.load_allowed_devices()
        self.device_limits = self.load_device_limits()
        
        # Create config directory if it doesn't exist
        os.makedirs(config_dir, exist_ok=True)
    
    def load_blocked_devices(self):
        """Load blocked devices from file"""
        try:
            if os.path.exists(self.blocked_devices_file):
                with open(self.blocked_devices_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading blocked devices: {e}")
        return {}
    
    def load_allowed_devices(self):
        """Load allowed devices from file"""
        try:
            if os.path.exists(self.allowed_devices_file):
                with open(self.allowed_devices_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading allowed devices: {e}")
        return {}
    
    def load_device_limits(self):
        """Load device bandwidth limits from file"""
        try:
            if os.path.exists(self.device_limits_file):
                with open(self.device_limits_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading device limits: {e}")
        return {}
    
    def save_blocked_devices(self):
        """Save blocked devices to file"""
        try:
            with open(self.blocked_devices_file, 'w') as f:
                json.dump(self.blocked_devices, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving blocked devices: {e}")
            return False
    
    def save_allowed_devices(self):
        """Save allowed devices to file"""
        try:
            with open(self.allowed_devices_file, 'w') as f:
                json.dump(self.allowed_devices, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving allowed devices: {e}")
            return False
    
    def save_device_limits(self):
        """Save device limits to file"""
        try:
            with open(self.device_limits_file, 'w') as f:
                json.dump(self.device_limits, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving device limits: {e}")
            return False
    
    def block_device_linux(self, mac_address, ip_address=None):
        """Block device on Linux using iptables"""
        try:
            # Block by MAC address
            cmd = ['sudo', 'iptables', '-A', 'FORWARD', '-m', 'mac', 
                   '--mac-source', mac_address, '-j', 'DROP']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Also block by IP if available
                if ip_address:
                    cmd_ip = ['sudo', 'iptables', '-A', 'FORWARD', '-s', ip_address, '-j', 'DROP']
                    subprocess.run(cmd_ip, capture_output=True, text=True)
                return True
            return False
        except Exception as e:
            print(f"Error blocking device on Linux: {e}")
            return False
    
    def unblock_device_linux(self, mac_address, ip_address=None):
        """Unblock device on Linux using iptables"""
        try:
            # Remove MAC-based block
            cmd = ['sudo', 'iptables', '-D', 'FORWARD', '-m', 'mac', 
                   '--mac-source', mac_address, '-j', 'DROP']
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Remove IP-based block if available
            if ip_address:
                cmd_ip = ['sudo', 'iptables', '-D', 'FORWARD', '-s', ip_address, '-j', 'DROP']
                subprocess.run(cmd_ip, capture_output=True, text=True)
            
            return result.returncode == 0
        except Exception as e:
            print(f"Error unblocking device on Linux: {e}")
            return False
    
    def block_device_windows(self, mac_address, ip_address=None):
        """Block device on Windows using netsh"""
        try:
            if ip_address:
                # Block by IP address
                cmd = ['netsh', 'advfirewall', 'firewall', 'add', 'rule', 
                       f'name=Block_{mac_address}', 'dir=in', 'action=block', 
                       f'remoteip={ip_address}']
                result = subprocess.run(cmd, capture_output=True, text=True)
                return result.returncode == 0
            return False
        except Exception as e:
            print(f"Error blocking device on Windows: {e}")
            return False
    
    def unblock_device_windows(self, mac_address, ip_address=None):
        """Unblock device on Windows using netsh"""
        try:
            # Remove firewall rule
            cmd = ['netsh', 'advfirewall', 'firewall', 'delete', 'rule', 
                   f'name=Block_{mac_address}']
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"Error unblocking device on Windows: {e}")
            return False
    
    def disconnect_device_windows(self, mac_address):
        """Disconnect device from Windows hosted network"""
        try:
            # Windows doesn't have direct MAC-based disconnect, need to restart hotspot
            print(f"Cannot directly disconnect {mac_address} on Windows. Consider restarting hotspot.")
            return False
        except Exception as e:
            print(f"Error disconnecting device on Windows: {e}")
            return False
    
    def disconnect_device_linux(self, mac_address):
        """Disconnect device from Linux hotspot"""
        try:
            # Force deauth using hostapd_cli if available
            cmd = ['sudo', 'hostapd_cli', 'deauthenticate', mac_address]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0
        except Exception as e:
            print(f"Error disconnecting device on Linux: {e}")
            return False
    
    def block_device(self, mac_address, device_name=None, ip_address=None):
        """Block a device by MAC address"""
        os_type = platform.system()
        
        if os_type == 'Linux':
            success = self.block_device_linux(mac_address, ip_address)
        elif os_type == 'Windows':
            success = self.block_device_windows(mac_address, ip_address)
        else:
            print(f"Unsupported OS: {os_type}")
            return False
        
        if success:
            self.blocked_devices[mac_address] = {
                'device_name': device_name or 'Unknown',
                'ip_address': ip_address,
                'blocked_time': datetime.now().isoformat(),
                'reason': 'Manual block'
            }
            self.save_blocked_devices()
            print(f"Device {mac_address} blocked successfully")
            return True
        else:
            print(f"Failed to block device {mac_address}")
            return False
    
    def unblock_device(self, mac_address):
        """Unblock a device by MAC address"""
        os_type = platform.system()
        
        ip_address = None
        if mac_address in self.blocked_devices:
            ip_address = self.blocked_devices[mac_address].get('ip_address')
        
        if os_type == 'Linux':
            success = self.unblock_device_linux(mac_address, ip_address)
        elif os_type == 'Windows':
            success = self.unblock_device_windows(mac_address, ip_address)
        else:
            print(f"Unsupported OS: {os_type}")
            return False
        
        if success:
            if mac_address in self.blocked_devices:
                del self.blocked_devices[mac_address]
                self.save_blocked_devices()
            print(f"Device {mac_address} unblocked successfully")
            return True
        else:
            print(f"Failed to unblock device {mac_address}")
            return False
    
    def disconnect_device(self, mac_address):
        """Disconnect a device from the hotspot"""
        os_type = platform.system()
        
        if os_type == 'Linux':
            return self.disconnect_device_linux(mac_address)
        elif os_type == 'Windows':
            return self.disconnect_device_windows(mac_address)
        else:
            print(f"Unsupported OS: {os_type}")
            return False
    
    def set_device_limit(self, mac_address, upload_limit_kbps=None, download_limit_kbps=None):
        """Set bandwidth limits for a device"""
        self.device_limits[mac_address] = {
            'upload_limit_kbps': upload_limit_kbps,
            'download_limit_kbps': download_limit_kbps,
            'set_time': datetime.now().isoformat()
        }
        self.save_device_limits()
        
        # Apply limits using tc (Linux) or netsh (Windows)
        return self.apply_bandwidth_limits(mac_address, upload_limit_kbps, download_limit_kbps)
    
    def apply_bandwidth_limits(self, mac_address, upload_limit_kbps, download_limit_kbps):
        """Apply bandwidth limits to device"""
        os_type = platform.system()
        
        if os_type == 'Linux':
            return self.apply_limits_linux(mac_address, upload_limit_kbps, download_limit_kbps)
        elif os_type == 'Windows':
            print("Bandwidth limiting not directly supported on Windows")
            return False
        else:
            return False
    
    def apply_limits_linux(self, mac_address, upload_limit_kbps, download_limit_kbps):
        """Apply bandwidth limits on Linux using tc"""
        try:
            interface = 'ap0'  # Default AP interface, may need adjustment
            
            if upload_limit_kbps:
                # Create upload limit
                cmd = ['sudo', 'tc', 'qdisc', 'add', 'dev', interface, 'root', 'handle', '1:', 'htb']
                subprocess.run(cmd, capture_output=True)
                
                cmd = ['sudo', 'tc', 'class', 'add', 'dev', interface, 'parent', '1:', 
                       'classid', '1:1', 'htb', 'rate', f'{upload_limit_kbps}kbit']
                subprocess.run(cmd, capture_output=True)
            
            return True
        except Exception as e:
            print(f"Error applying bandwidth limits: {e}")
            return False
    
    def add_to_whitelist(self, mac_address, device_name=None):
        """Add device to allowed list"""
        self.allowed_devices[mac_address] = {
            'device_name': device_name or 'Unknown',
            'added_time': datetime.now().isoformat(),
            'always_allow': True
        }
        self.save_allowed_devices()
        print(f"Device {mac_address} added to whitelist")
    
    def remove_from_whitelist(self, mac_address):
        """Remove device from allowed list"""
        if mac_address in self.allowed_devices:
            del self.allowed_devices[mac_address]
            self.save_allowed_devices()
            print(f"Device {mac_address} removed from whitelist")
            return True
        return False
    
    def is_device_blocked(self, mac_address):
        """Check if device is blocked"""
        return mac_address in self.blocked_devices
    
    def is_device_whitelisted(self, mac_address):
        """Check if device is whitelisted"""
        return mac_address in self.allowed_devices
    
    def get_device_info(self, mac_address):
        """Get comprehensive device information"""
        info = {
            'mac_address': mac_address,
            'blocked': self.is_device_blocked(mac_address),
            'whitelisted': self.is_device_whitelisted(mac_address),
            'has_limits': mac_address in self.device_limits
        }
        
        if info['blocked']:
            info['block_info'] = self.blocked_devices[mac_address]
        
        if info['whitelisted']:
            info['whitelist_info'] = self.allowed_devices[mac_address]
        
        if info['has_limits']:
            info['limits'] = self.device_limits[mac_address]
        
        return info
    
    def list_all_managed_devices(self):
        """List all devices with management information"""
        all_devices = set()
        all_devices.update(self.blocked_devices.keys())
        all_devices.update(self.allowed_devices.keys())
        all_devices.update(self.device_limits.keys())
        
        devices_info = []
        for mac in all_devices:
            devices_info.append(self.get_device_info(mac))
        
        return devices_info
    
    def clear_all_blocks(self):
        """Clear all device blocks"""
        blocked_macs = list(self.blocked_devices.keys())
        success_count = 0
        
        for mac in blocked_macs:
            if self.unblock_device(mac):
                success_count += 1
        
        return success_count, len(blocked_macs)

def main():
    """Main function for testing device manager"""
    manager = DeviceManager()
    
    while True:
        print("\n--- Device Manager ---")
        print("1. List managed devices")
        print("2. Block device")
        print("3. Unblock device")
        print("4. Add to whitelist")
        print("5. Remove from whitelist")
        print("6. Set bandwidth limits")
        print("7. Disconnect device")
        print("8. Clear all blocks")
        print("0. Exit")
        
        choice = input("Select option: ").strip()
        
        if choice == '1':
            devices = manager.list_all_managed_devices()
            for device in devices:
                print(f"MAC: {device['mac_address']}")
                print(f"  Blocked: {device['blocked']}")
                print(f"  Whitelisted: {device['whitelisted']}")
                print(f"  Has Limits: {device['has_limits']}")
                print()
        
        elif choice == '2':
            mac = input("Enter MAC address to block: ").strip()
            name = input("Enter device name (optional): ").strip() or None
            ip = input("Enter IP address (optional): ").strip() or None
            manager.block_device(mac, name, ip)
        
        elif choice == '3':
            mac = input("Enter MAC address to unblock: ").strip()
            manager.unblock_device(mac)
        
        elif choice == '4':
            mac = input("Enter MAC address to whitelist: ").strip()
            name = input("Enter device name (optional): ").strip() or None
            manager.add_to_whitelist(mac, name)
        
        elif choice == '5':
            mac = input("Enter MAC address to remove from whitelist: ").strip()
            manager.remove_from_whitelist(mac)
        
        elif choice == '6':
            mac = input("Enter MAC address: ").strip()
            upload = input("Upload limit (kbps, optional): ").strip()
            download = input("Download limit (kbps, optional): ").strip()
            
            upload_limit = int(upload) if upload else None
            download_limit = int(download) if download else None
            
            manager.set_device_limit(mac, upload_limit, download_limit)
        
        elif choice == '7':
            mac = input("Enter MAC address to disconnect: ").strip()
            manager.disconnect_device(mac)
        
        elif choice == '8':
            success, total = manager.clear_all_blocks()
            print(f"Cleared {success}/{total} blocks")
        
        elif choice == '0':
            break

if __name__ == "__main__":
    main()
