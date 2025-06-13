#!/usr/bin/env python3
"""
System Monitor for Hotspot
Monitors system resources, performance, and health metrics
"""

import psutil
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque
import json

class SystemMonitor:
    def __init__(self, history_size: int = 100):
        self.logger = logging.getLogger(__name__)
        self.history_size = history_size
        self.monitoring = False
        self.monitor_thread = None
        
        # Data storage
        self.cpu_history = deque(maxlen=history_size)
        self.memory_history = deque(maxlen=history_size)
        self.network_history = deque(maxlen=history_size)
        self.temperature_history = deque(maxlen=history_size)
        
        # Monitoring interval
        self.update_interval = 1.0  # seconds
        
        # Thresholds for alerts
        self.thresholds = {
            'cpu_warning': 80.0,
            'cpu_critical': 95.0,
            'memory_warning': 80.0,
            'memory_critical': 95.0,
            'temperature_warning': 70.0,
            'temperature_critical': 85.0,
            'disk_warning': 85.0,
            'disk_critical': 95.0
        }
        
        # Alert tracking
        self.alerts = []
        self.last_alert_time = {}
        
    def start_monitoring(self):
        """Start the system monitoring thread"""
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            self.logger.info("System monitoring started")
    
    def stop_monitoring(self):
        """Stop the system monitoring thread"""
        self.monitoring = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        self.logger.info("System monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                timestamp = datetime.now()
                
                # Collect metrics
                cpu_data = self._get_cpu_metrics(timestamp)
                memory_data = self._get_memory_metrics(timestamp)
                network_data = self._get_network_metrics(timestamp)
                temperature_data = self._get_temperature_metrics(timestamp)
                
                # Store in history
                self.cpu_history.append(cpu_data)
                self.memory_history.append(memory_data)
                self.network_history.append(network_data)
                self.temperature_history.append(temperature_data)
                
                # Check for alerts
                self._check_alerts(cpu_data, memory_data, temperature_data)
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.update_interval)
    
    def _get_cpu_metrics(self, timestamp: datetime) -> Dict:
        """Get CPU usage metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            load_avg = None
            try:
                load_avg = psutil.getloadavg()
            except AttributeError:
                # Windows doesn't have load average
                pass
            
            return {
                'timestamp': timestamp,
                'cpu_percent': cpu_percent,
                'cpu_count': cpu_count,
                'cpu_freq_current': cpu_freq.current if cpu_freq else None,
                'cpu_freq_max': cpu_freq.max if cpu_freq else None,
                'load_avg_1min': load_avg[0] if load_avg else None,
                'load_avg_5min': load_avg[1] if load_avg else None,
                'load_avg_15min': load_avg[2] if load_avg else None
            }
        except Exception as e:
            self.logger.error(f"Error getting CPU metrics: {e}")
            return {'timestamp': timestamp, 'error': str(e)}
    
    def _get_memory_metrics(self, timestamp: datetime) -> Dict:
        """Get memory usage metrics"""
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            return {
                'timestamp': timestamp,
                'memory_total': memory.total,
                'memory_available': memory.available,
                'memory_used': memory.used,
                'memory_percent': memory.percent,
                'swap_total': swap.total,
                'swap_used': swap.used,
                'swap_percent': swap.percent
            }
        except Exception as e:
            self.logger.error(f"Error getting memory metrics: {e}")
            return {'timestamp': timestamp, 'error': str(e)}
    
    def _get_network_metrics(self, timestamp: datetime) -> Dict:
        """Get network interface metrics"""
        try:
            net_io = psutil.net_io_counters()
            net_connections = len(psutil.net_connections())
            
            # Get per-interface stats
            net_if_stats = {}
            for interface, stats in psutil.net_io_counters(pernic=True).items():
                net_if_stats[interface] = {
                    'bytes_sent': stats.bytes_sent,
                    'bytes_recv': stats.bytes_recv,
                    'packets_sent': stats.packets_sent,
                    'packets_recv': stats.packets_recv,
                    'errin': stats.errin,
                    'errout': stats.errout,
                    'dropin': stats.dropin,
                    'dropout': stats.dropout
                }
            
            return {
                'timestamp': timestamp,
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv,
                'connections_count': net_connections,
                'interfaces': net_if_stats
            }
        except Exception as e:
            self.logger.error(f"Error getting network metrics: {e}")
            return {'timestamp': timestamp, 'error': str(e)}
    
    def _get_temperature_metrics(self, timestamp: datetime) -> Dict:
        """Get system temperature metrics"""
        try:
            temperatures = {}
            
            # Try to get temperature sensors
            try:
                temps = psutil.sensors_temperatures()
                for sensor_name, sensor_list in temps.items():
                    temperatures[sensor_name] = []
                    for sensor in sensor_list:
                        temperatures[sensor_name].append({
                            'label': sensor.label or 'Unknown',
                            'current': sensor.current,
                            'high': sensor.high,
                            'critical': sensor.critical
                        })
            except AttributeError:
                # Temperature sensors not available
                pass
            
            return {
                'timestamp': timestamp,
                'temperatures': temperatures
            }
        except Exception as e:
            self.logger.error(f"Error getting temperature metrics: {e}")
            return {'timestamp': timestamp, 'error': str(e)}
    
    def _check_alerts(self, cpu_data: Dict, memory_data: Dict, temperature_data: Dict):
        """Check for system alerts based on thresholds"""
        current_time = datetime.now()
        
        # CPU alerts
        if 'cpu_percent' in cpu_data:
            cpu_percent = cpu_data['cpu_percent']
            if cpu_percent >= self.thresholds['cpu_critical']:
                self._add_alert('cpu_critical', f"CPU usage critical: {cpu_percent:.1f}%", current_time)
            elif cpu_percent >= self.thresholds['cpu_warning']:
                self._add_alert('cpu_warning', f"CPU usage high: {cpu_percent:.1f}%", current_time)
        
        # Memory alerts
        if 'memory_percent' in memory_data:
            memory_percent = memory_data['memory_percent']
            if memory_percent >= self.thresholds['memory_critical']:
                self._add_alert('memory_critical', f"Memory usage critical: {memory_percent:.1f}%", current_time)
            elif memory_percent >= self.thresholds['memory_warning']:
                self._add_alert('memory_warning', f"Memory usage high: {memory_percent:.1f}%", current_time)
        
        # Temperature alerts
        if 'temperatures' in temperature_data:
            for sensor_name, sensor_list in temperature_data['temperatures'].items():
                for sensor in sensor_list:
                    temp = sensor['current']
                    if temp and temp >= self.thresholds['temperature_critical']:
                        self._add_alert('temperature_critical', 
                                      f"Temperature critical: {sensor_name} {temp:.1f}°C", current_time)
                    elif temp and temp >= self.thresholds['temperature_warning']:
                        self._add_alert('temperature_warning', 
                                      f"Temperature high: {sensor_name} {temp:.1f}°C", current_time)
    
    def _add_alert(self, alert_type: str, message: str, timestamp: datetime):
        """Add an alert with rate limiting"""
        # Rate limit alerts (don't repeat same alert type within 5 minutes)
        if alert_type in self.last_alert_time:
            time_diff = timestamp - self.last_alert_time[alert_type]
            if time_diff < timedelta(minutes=5):
                return
        
        alert = {
            'type': alert_type,
            'message': message,
            'timestamp': timestamp,
            'level': 'critical' if 'critical' in alert_type else 'warning'
        }
        
        self.alerts.append(alert)
        self.last_alert_time[alert_type] = timestamp
        
        # Keep only recent alerts (last 100)
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
        
        self.logger.warning(f"System alert: {message}")
    
    def get_current_metrics(self) -> Dict:
        """Get current system metrics"""
        timestamp = datetime.now()
        
        return {
            'cpu': self._get_cpu_metrics(timestamp),
            'memory': self._get_memory_metrics(timestamp),
            'network': self._get_network_metrics(timestamp),
            'temperature': self._get_temperature_metrics(timestamp),
            'disk': self._get_disk_metrics(timestamp)
        }
    
    def _get_disk_metrics(self, timestamp: datetime) -> Dict:
        """Get disk usage metrics"""
        try:
            disk_usage = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            return {
                'timestamp': timestamp,
                'disk_total': disk_usage.total,
                'disk_used': disk_usage.used,
                'disk_free': disk_usage.free,
                'disk_percent': disk_usage.used / disk_usage.total * 100,
                'disk_read_bytes': disk_io.read_bytes if disk_io else None,
                'disk_write_bytes': disk_io.write_bytes if disk_io else None,
                'disk_read_count': disk_io.read_count if disk_io else None,
                'disk_write_count': disk_io.write_count if disk_io else None
            }
        except Exception as e:
            self.logger.error(f"Error getting disk metrics: {e}")
            return {'timestamp': timestamp, 'error': str(e)}
    
    def get_history(self, metric_type: str, duration_minutes: int = 60) -> List[Dict]:
        """Get historical data for a specific metric type"""
        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        
        if metric_type == 'cpu':
            history = self.cpu_history
        elif metric_type == 'memory':
            history = self.memory_history
        elif metric_type == 'network':
            history = self.network_history
        elif metric_type == 'temperature':
            history = self.temperature_history
        else:
            return []
        
        # Filter by time
        filtered_history = [
            item for item in history 
            if item.get('timestamp') and item['timestamp'] >= cutoff_time
        ]
        
        return list(filtered_history)
    
    def get_alerts(self, level: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Get recent alerts"""
        alerts = self.alerts[-limit:] if limit else self.alerts
        
        if level:
            alerts = [alert for alert in alerts if alert['level'] == level]
        
        return sorted(alerts, key=lambda x: x['timestamp'], reverse=True)
    
    def clear_alerts(self):
        """Clear all alerts"""
        self.alerts.clear()
        self.last_alert_time.clear()
        self.logger.info("System alerts cleared")
    
    def get_system_summary(self) -> Dict:
        """Get a summary of system status"""
        current_metrics = self.get_current_metrics()
        recent_alerts = self.get_alerts(limit=10)
        
        # Calculate uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        # Get system info
        system_info = {
            'hostname': psutil.users()[0].name if psutil.users() else 'Unknown',
            'platform': psutil.LINUX if hasattr(psutil, 'LINUX') else 'Unknown',
            'boot_time': boot_time,
            'uptime_seconds': uptime.total_seconds(),
            'uptime_formatted': str(uptime).split('.')[0]  # Remove microseconds
        }
        
        return {
            'system_info': system_info,
            'current_metrics': current_metrics,
            'recent_alerts': recent_alerts,
            'alert_counts': {
                'critical': len([a for a in recent_alerts if a['level'] == 'critical']),
                'warning': len([a for a in recent_alerts if a['level'] == 'warning'])
            },
            'monitoring_active': self.monitoring
        }
    
    def export_metrics(self, filename: str, duration_hours: int = 24):
        """Export metrics to JSON file"""
        try:
            duration_minutes = duration_hours * 60
            
            export_data = {
                'export_time': datetime.now().isoformat(),
                'duration_hours': duration_hours,
                'cpu_history': [
                    {**item, 'timestamp': item['timestamp'].isoformat()} 
                    for item in self.get_history('cpu', duration_minutes)
                ],
                'memory_history': [
                    {**item, 'timestamp': item['timestamp'].isoformat()} 
                    for item in self.get_history('memory', duration_minutes)
                ],
                'network_history': [
                    {**item, 'timestamp': item['timestamp'].isoformat()} 
                    for item in self.get_history('network', duration_minutes)
                ],
                'temperature_history': [
                    {**item, 'timestamp': item['timestamp'].isoformat()} 
                    for item in self.get_history('temperature', duration_minutes)
                ],
                'alerts': [
                    {**alert, 'timestamp': alert['timestamp'].isoformat()} 
                    for alert in self.alerts
                ]
            }
            
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            self.logger.info(f"Metrics exported to {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")
            return False

if __name__ == "__main__":
    # Test the system monitor
    logging.basicConfig(level=logging.INFO)
    
    monitor = SystemMonitor()
    
    # Start monitoring
    monitor.start_monitoring()
    
    try:
        # Run for a short time to collect some data
        time.sleep(10)
        
        # Get current metrics
        print("Current System Metrics:")
        current = monitor.get_current_metrics()
        print(f"CPU: {current['cpu'].get('cpu_percent', 'N/A')}%")
        print(f"Memory: {current['memory'].get('memory_percent', 'N/A')}%")
        
        # Get system summary
        print("\nSystem Summary:")
        summary = monitor.get_system_summary()
        print(f"Uptime: {summary['system_info']['uptime_formatted']}")
        print(f"Alerts: {summary['alert_counts']}")
        
    finally:
        monitor.stop_monitoring()
