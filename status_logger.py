#!/usr/bin/env python3
"""
Status Logger and Manager Script for Hotspot Tool
Handles logging, status tracking, and event management
"""

import logging
import json
import os
import time
import threading
from datetime import datetime, timedelta
from collections import deque
import subprocess
import platform

class StatusLogger:
    def __init__(self, config_dir='hotspot_config', log_dir='logs'):
        self.config_dir = config_dir
        self.log_dir = log_dir
        self.status_file = os.path.join(config_dir, 'hotspot_status.json')
        self.events_file = os.path.join(config_dir, 'events.json')
        
        # Create directories
        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        
        # Initialize logging
        self.setup_logging()
        
        # Status tracking
        self.current_status = self.load_status()
        self.events = self.load_events()
        self.status_history = deque(maxlen=1000)  # Keep last 1000 status updates
        
        # Monitoring thread
        self.monitoring = False
        self.monitor_thread = None
        
        self.logger = logging.getLogger('hotspot_status')
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_file = os.path.join(self.log_dir, 'hotspot.log')
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        
        # Setup logger
        logger = logging.getLogger('hotspot_status')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Prevent duplicate logs
        logger.propagate = False
    
    def load_status(self):
        """Load current status from file"""
        default_status = {
            'hotspot_active': False,
            'ssid': '',
            'connected_devices': 0,
            'uptime': 0,
            'data_usage': {
                'total_sent': 0,
                'total_received': 0,
                'session_sent': 0,
                'session_received': 0
            },
            'last_started': None,
            'last_stopped': None,
            'error_count': 0,
            'last_error': None,
            'performance': {
                'cpu_usage': 0,
                'memory_usage': 0,
                'network_load': 0
            }
        }
        
        try:
            if os.path.exists(self.status_file):
                with open(self.status_file, 'r') as f:
                    status = json.load(f)
                # Merge with defaults
                for key, value in default_status.items():
                    if key not in status:
                        status[key] = value
                return status
        except Exception as e:
            self.logger.error(f"Error loading status: {e}")
        
        return default_status
    
    def load_events(self):
        """Load events history from file"""
        try:
            if os.path.exists(self.events_file):
                with open(self.events_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading events: {e}")
        return []
    
    def save_status(self):
        """Save current status to file"""
        try:
            self.current_status['last_updated'] = datetime.now().isoformat()
            with open(self.status_file, 'w') as f:
                json.dump(self.current_status, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error saving status: {e}")
            return False
    
    def save_events(self):
        """Save events to file"""
        try:
            # Keep only last 1000 events
            if len(self.events) > 1000:
                self.events = self.events[-1000:]
            
            with open(self.events_file, 'w') as f:
                json.dump(self.events, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error saving events: {e}")
            return False
    
    def log_event(self, event_type, message, level='INFO', details=None):
        """Log an event with timestamp"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'level': level,
            'message': message,
            'details': details or {}
        }
        
        self.events.append(event)
        self.save_events()
        
        # Also log to file
        if level == 'ERROR':
            self.logger.error(f"{event_type}: {message}")
        elif level == 'WARNING':
            self.logger.warning(f"{event_type}: {message}")
        else:
            self.logger.info(f"{event_type}: {message}")
    
    def update_status(self, **kwargs):
        """Update current status"""
        updated = False
        for key, value in kwargs.items():
            if key in self.current_status and self.current_status[key] != value:
                old_value = self.current_status[key]
                self.current_status[key] = value
                updated = True
                
                # Log significant status changes
                if key == 'hotspot_active':
                    if value:
                        self.log_event('HOTSPOT_START', f'Hotspot activated: {self.current_status.get("ssid", "Unknown")}')
                        self.current_status['last_started'] = datetime.now().isoformat()
                    else:
                        self.log_event('HOTSPOT_STOP', 'Hotspot deactivated')
                        self.current_status['last_stopped'] = datetime.now().isoformat()
                elif key == 'connected_devices':
                    if value > old_value:
                        self.log_event('DEVICE_CONNECT', f'Device connected (total: {value})')
                    elif value < old_value:
                        self.log_event('DEVICE_DISCONNECT', f'Device disconnected (total: {value})')
        
        if updated:
            # Add to history
            status_snapshot = self.current_status.copy()
            status_snapshot['timestamp'] = datetime.now().isoformat()
            self.status_history.append(status_snapshot)
            
            self.save_status()
    
    def get_hotspot_status_linux(self):
        """Get hotspot status on Linux"""
        try:
            # Check if hostapd is running
            result = subprocess.run(['pgrep', 'hostapd'], capture_output=True, text=True)
            hostapd_running = result.returncode == 0
            
            # Check network interface status
            result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True)
            interface_up = 'ap0' in result.stdout and 'state UP' in result.stdout
            
            return hostapd_running and interface_up
        except Exception as e:
            self.logger.error(f"Error checking Linux hotspot status: {e}")
            return False
    
    def get_hotspot_status_windows(self):
        """Get hotspot status on Windows"""
        try:
            result = subprocess.run(['netsh', 'wlan', 'show', 'hostednetwork'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                output = result.stdout.lower()
                return 'status' in output and 'started' in output
        except Exception as e:
            self.logger.error(f"Error checking Windows hotspot status: {e}")
        return False
    
    def get_system_performance(self):
        """Get system performance metrics"""
        try:
            import psutil
            return {
                'cpu_usage': psutil.cpu_percent(interval=1),
                'memory_usage': psutil.virtual_memory().percent,
                'disk_usage': psutil.disk_usage('/').percent,
                'network_load': self.calculate_network_load()
            }
        except ImportError:
            return {
                'cpu_usage': 0,
                'memory_usage': 0,
                'disk_usage': 0,
                'network_load': 0
            }
    
    def calculate_network_load(self):
        """Calculate current network load percentage"""
        try:
            import psutil
            # Simple network load calculation based on bytes/sec
            stats1 = psutil.net_io_counters()
            time.sleep(1)
            stats2 = psutil.net_io_counters()
            
            bytes_per_sec = (stats2.bytes_sent + stats2.bytes_recv) - (stats1.bytes_sent + stats1.bytes_recv)
            # Assume 100 Mbps connection for percentage calculation
            max_bytes_per_sec = 12500000  # 100 Mbps in bytes
            
            return min(100, (bytes_per_sec / max_bytes_per_sec) * 100)
        except:
            return 0
    
    def monitor_status(self):
        """Monitor hotspot status in background"""
        while self.monitoring:
            try:
                # Check hotspot status
                os_type = platform.system()
                if os_type == 'Linux':
                    active = self.get_hotspot_status_linux()
                elif os_type == 'Windows':
                    active = self.get_hotspot_status_windows()
                else:
                    active = False
                
                # Get performance metrics
                performance = self.get_system_performance()
                
                # Update status
                self.update_status(
                    hotspot_active=active,
                    performance=performance
                )
                
                # Calculate uptime
                if active and self.current_status.get('last_started'):
                    start_time = datetime.fromisoformat(self.current_status['last_started'])
                    uptime = (datetime.now() - start_time).total_seconds()
                    self.update_status(uptime=uptime)
                
            except Exception as e:
                self.logger.error(f"Error in status monitoring: {e}")
                self.current_status['error_count'] += 1
                self.current_status['last_error'] = str(e)
            
            time.sleep(5)  # Update every 5 seconds
    
    def start_monitoring(self):
        """Start status monitoring"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self.monitor_status)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            self.log_event('MONITOR_START', 'Status monitoring started')
    
    def stop_monitoring(self):
        """Stop status monitoring"""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=1)
            self.log_event('MONITOR_STOP', 'Status monitoring stopped')
    
    def get_status_summary(self):
        """Get status summary"""
        summary = {
            'current_status': self.current_status.copy(),
            'recent_events': self.events[-10:] if self.events else [],
            'monitoring_active': self.monitoring,
            'uptime_formatted': self.format_uptime(self.current_status.get('uptime', 0)),
            'data_usage_formatted': self.format_data_usage(self.current_status.get('data_usage', {}))
        }
        return summary
    
    def format_uptime(self, seconds):
        """Format uptime in human readable format"""
        if seconds <= 0:
            return "Not running"
        
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def format_data_usage(self, data_usage):
        """Format data usage in human readable format"""
        def format_bytes(bytes_count):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if bytes_count < 1024.0:
                    return f"{bytes_count:.2f} {unit}"
                bytes_count /= 1024.0
            return f"{bytes_count:.2f} PB"
        
        return {
            'total_sent': format_bytes(data_usage.get('total_sent', 0)),
            'total_received': format_bytes(data_usage.get('total_received', 0)),
            'session_sent': format_bytes(data_usage.get('session_sent', 0)),
            'session_received': format_bytes(data_usage.get('session_received', 0))
        }
    
    def get_events_by_type(self, event_type, limit=50):
        """Get events filtered by type"""
        filtered_events = [event for event in self.events if event['type'] == event_type]
        return filtered_events[-limit:] if filtered_events else []
    
    def get_events_by_timerange(self, hours=24):
        """Get events from the last N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)