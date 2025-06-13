#!/usr/bin/env python3
"""
Linux Hotspot Manager - Production Ready Application
A comprehensive hotspot management tool for Linux systems
"""

import sys
import os
import subprocess
import threading
import time
import json
import re
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox,
        QTextEdit, QGroupBox, QCheckBox, QSpinBox, QSlider,
        QTabWidget, QTableWidget, QTableWidgetItem, QProgressBar,
        QSystemTrayIcon, QMenu, QAction, QMessageBox, QSplashScreen,
        QFrame, QScrollArea, QDialog, QDialogButtonBox, QFormLayout
    )
    from PyQt5.QtCore import (
        QThread, pyqtSignal, QTimer, Qt, QSettings, QSize,
        QPropertyAnimation, QEasingCurve, QRect
    )
    from PyQt5.QtGui import (
        QFont, QIcon, QPixmap, QPainter, QColor, QPalette,
        QLinearGradient, QBrush, QMovie
    )
except ImportError:
    print("PyQt5 not found. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "PyQt5"], check=True)
    from PyQt5.QtWidgets import *
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *

import psutil
import netifaces


class NetworkInterface:
    """Manages network interface detection and configuration"""
    
    @staticmethod
    def get_wireless_interfaces() -> List[str]:
        """Get all available wireless interfaces"""
        interfaces = []
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True, stderr=subprocess.DEVNULL)
            for line in result.stdout.split('\n'):
                if 'IEEE 802.11' in line:
                    interface = line.split()[0]
                    interfaces.append(interface)
        except (subprocess.SubprocessError, FileNotFoundError):
            # Fallback method
            for interface in netifaces.interfaces():
                if interface.startswith(('wlan', 'wlp')):
                    interfaces.append(interface)
        return interfaces
    
    @staticmethod
    def get_ethernet_interfaces() -> List[str]:
        """Get all available ethernet interfaces"""
        interfaces = []
        for interface in netifaces.interfaces():
            if interface.startswith(('eth', 'enp', 'eno')):
                interfaces.append(interface)
        return interfaces
    
    @staticmethod
    def get_interface_info(interface: str) -> Dict:
        """Get detailed information about a network interface"""
        info = {'name': interface, 'ip': None, 'status': 'down'}
        try:
            addrs = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addrs:
                info['ip'] = addrs[netifaces.AF_INET][0]['addr']
                info['status'] = 'up'
        except Exception:
            pass
        return info


class HotspotManager:
    """Core hotspot management functionality"""
    
    def __init__(self):
        self.is_active = False
        self.connection_name = "HotspotManager"
        self.current_config = {}
        
    def check_dependencies(self) -> Tuple[bool, List[str]]:
        """Check if required tools are available"""
        required_tools = ['nmcli', 'hostapd', 'dnsmasq', 'iptables']
        missing = []
        
        for tool in required_tools:
            try:
                subprocess.run(['which', tool], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                missing.append(tool)
        
        return len(missing) == 0, missing
    
    def create_hotspot(self, config: Dict) -> Tuple[bool, str]:
        """Create and start the hotspot"""
        try:
            # Stop any existing hotspot
            self.stop_hotspot()
            
            # Validate configuration
            if not self._validate_config(config):
                return False, "Invalid configuration parameters"
            
            # Create the hotspot connection
            cmd = [
                'nmcli', 'device', 'wifi', 'hotspot',
                'ifname', config['interface'],
                'con-name', self.connection_name,
                'ssid', config['ssid'],
                'password', config['password']
            ]
            
            if config.get('band'):
                cmd.extend(['band', config['band']])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return False, f"Failed to create hotspot: {result.stderr}"
            
            # Configure additional settings
            self._configure_advanced_settings(config)
            
            # Start internet sharing
            if config.get('share_internet'):
                self._setup_internet_sharing(config)
            
            self.is_active = True
            self.current_config = config.copy()
            
            return True, "Hotspot created successfully"
            
        except Exception as e:
            return False, f"Error creating hotspot: {str(e)}"
    
    def stop_hotspot(self) -> Tuple[bool, str]:
        """Stop the hotspot"""
        try:
            # Stop the connection
            subprocess.run(['nmcli', 'connection', 'down', self.connection_name], 
                         capture_output=True)
            
            # Delete the connection
            subprocess.run(['nmcli', 'connection', 'delete', self.connection_name], 
                         capture_output=True)
            
            # Clean up internet sharing
            self._cleanup_internet_sharing()
            
            self.is_active = False
            self.current_config = {}
            
            return True, "Hotspot stopped successfully"
            
        except Exception as e:
            return False, f"Error stopping hotspot: {str(e)}"
    
    def get_connected_devices(self) -> List[Dict]:
        """Get list of connected devices"""
        devices = []
        try:
            # Get DHCP leases
            lease_files = ['/var/lib/dhcp/dhcpd.leases', '/var/lib/dhcpcd5/dhcpcd.leases']
            
            for lease_file in lease_files:
                if os.path.exists(lease_file):
                    devices.extend(self._parse_dhcp_leases(lease_file))
            
            # Get ARP table
            arp_devices = self._get_arp_devices()
            
            # Merge and deduplicate
            device_map = {}
            for device in devices + arp_devices:
                mac = device.get('mac')
                if mac:
                    device_map[mac] = device
            
            return list(device_map.values())
            
        except Exception:
            return []
    
    def get_data_usage(self) -> Dict:
        """Get data usage statistics"""
        try:
            stats = psutil.net_io_counters(pernic=True)
            if self.current_config.get('interface') in stats:
                interface_stats = stats[self.current_config['interface']]
                return {
                    'bytes_sent': interface_stats.bytes_sent,
                    'bytes_recv': interface_stats.bytes_recv,
                    'packets_sent': interface_stats.packets_sent,
                    'packets_recv': interface_stats.packets_recv
                }
        except Exception:
            pass
        return {'bytes_sent': 0, 'bytes_recv': 0, 'packets_sent': 0, 'packets_recv': 0}
    
    def _validate_config(self, config: Dict) -> bool:
        """Validate hotspot configuration"""
        required_fields = ['interface', 'ssid', 'password']
        
        for field in required_fields:
            if not config.get(field):
                return False
        
        if len(config['password']) < 8:
            return False
            
        if len(config['ssid']) < 1 or len(config['ssid']) > 32:
            return False
            
        return True
    
    def _configure_advanced_settings(self, config: Dict):
        """Configure advanced hotspot settings"""
        try:
            # Set channel if specified
            if config.get('channel'):
                subprocess.run([
                    'nmcli', 'connection', 'modify', self.connection_name,
                    '802-11-wireless.channel', str(config['channel'])
                ], capture_output=True)
            
            # Set max clients if specified
            if config.get('max_clients'):
                # This would require hostapd configuration
                pass
                
        except Exception:
            pass
    
    def _setup_internet_sharing(self, config: Dict):
        """Setup internet connection sharing"""
        try:
            internet_interface = config.get('internet_interface')
            hotspot_interface = config['interface']
            
            if not internet_interface:
                return
            
            # Enable IP forwarding
            subprocess.run(['sysctl', 'net.ipv4.ip_forward=1'], capture_output=True)
            
            # Setup iptables rules
            subprocess.run([
                'iptables', '-t', 'nat', '-A', 'POSTROUTING',
                '-o', internet_interface, '-j', 'MASQUERADE'
            ], capture_output=True)
            
            subprocess.run([
                'iptables', '-A', 'FORWARD',
                '-i', internet_interface, '-o', hotspot_interface,
                '-m', 'state', '--state', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'
            ], capture_output=True)
            
            subprocess.run([
                'iptables', '-A', 'FORWARD',
                '-i', hotspot_interface, '-o', internet_interface,
                '-j', 'ACCEPT'
            ], capture_output=True)
            
        except Exception:
            pass
    
    def _cleanup_internet_sharing(self):
        """Clean up internet sharing configuration"""
        try:
            # Remove iptables rules
            subprocess.run(['iptables', '-t', 'nat', '-F'], capture_output=True)
            subprocess.run(['iptables', '-F', 'FORWARD'], capture_output=True)
        except Exception:
            pass
    
    def _parse_dhcp_leases(self, lease_file: str) -> List[Dict]:
        """Parse DHCP lease file"""
        devices = []
        try:
            with open(lease_file, 'r') as f:
                content = f.read()
                
            # Simple parsing for common lease formats
            lease_blocks = re.findall(r'lease ([\d.]+) {([^}]+)}', content)
            
            for ip, block in lease_blocks:
                device = {'ip': ip}
                
                mac_match = re.search(r'hardware ethernet ([^;]+);', block)
                if mac_match:
                    device['mac'] = mac_match.group(1)
                
                hostname_match = re.search(r'client-hostname "([^"]+)"', block)
                if hostname_match:
                    device['hostname'] = hostname_match.group(1)
                
                devices.append(device)
                
        except Exception:
            pass
        return devices
    
    def _get_arp_devices(self) -> List[Dict]:
        """Get devices from ARP table"""
        devices = []
        try:
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                match = re.search(r'([^\s]+)\s+\(([\d.]+)\)\s+at\s+([^\s]+)', line)
                if match:
                    hostname, ip, mac = match.groups()
                    devices.append({
                        'hostname': hostname,
                        'ip': ip,
                        'mac': mac
                    })
        except Exception:
            pass
        return devices


class MonitorThread(QThread):
    """Background thread for monitoring hotspot status and connected devices"""
    
    status_updated = pyqtSignal(dict)
    devices_updated = pyqtSignal(list)
    data_updated = pyqtSignal(dict)
    
    def __init__(self, hotspot_manager):
        super().__init__()
        self.hotspot_manager = hotspot_manager
        self.running = True
        
    def run(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Update status
                status = {
                    'is_active': self.hotspot_manager.is_active,
                    'config': self.hotspot_manager.current_config
                }
                self.status_updated.emit(status)
                
                # Update connected devices
                if self.hotspot_manager.is_active:
                    devices = self.hotspot_manager.get_connected_devices()
                    self.devices_updated.emit(devices)
                    
                    # Update data usage
                    data_usage = self.hotspot_manager.get_data_usage()
                    self.data_updated.emit(data_usage)
                
                time.sleep(2)  # Update every 2 seconds
                
            except Exception:
                pass
    
    def stop(self):
        """Stop the monitoring thread"""
        self.running = False
        self.quit()
        self.wait()


class SettingsDialog(QDialog):
    """Advanced settings dialog"""
    
    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setModal(True)
        self.resize(400, 300)
        
        self.settings = current_settings or {}
        self.init_ui()
        
    def init_ui(self):
        """Initialize the settings dialog UI"""
        layout = QVBoxLayout()
        
        # Create form layout
        form_layout = QFormLayout()
        
        # Channel selection
        self.channel_combo = QComboBox()
        self.channel_combo.addItems(['Auto'] + [str(i) for i in range(1, 15)])
        if self.settings.get('channel'):
            self.channel_combo.setCurrentText(str(self.settings['channel']))
        form_layout.addRow("Channel:", self.channel_combo)
        
        # Band selection
        self.band_combo = QComboBox()
        self.band_combo.addItems(['bg', 'a'])
        if self.settings.get('band'):
            self.band_combo.setCurrentText(self.settings['band'])
        form_layout.addRow("Band:", self.band_combo)
        
        # Max clients
        self.max_clients_spin = QSpinBox()
        self.max_clients_spin.setRange(1, 50)
        self.max_clients_spin.setValue(self.settings.get('max_clients', 10))
        form_layout.addRow("Max Clients:", self.max_clients_spin)
        
        # Hidden network
        self.hidden_check = QCheckBox()
        self.hidden_check.setChecked(self.settings.get('hidden', False))
        form_layout.addRow("Hidden Network:", self.hidden_check)
        
        layout.addLayout(form_layout)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def get_settings(self):
        """Get the configured settings"""
        settings = {}
        
        if self.channel_combo.currentText() != 'Auto':
            settings['channel'] = int(self.channel_combo.currentText())
            
        settings['band'] = self.band_combo.currentText()
        settings['max_clients'] = self.max_clients_spin.value()
        settings['hidden'] = self.hidden_check.isChecked()
        
        return settings


class HotspotGUI(QMainWindow):
    """Main GUI application"""
    
    def __init__(self):
        super().__init__()
        
        # Initialize core components
        self.hotspot_manager = HotspotManager()
        self.monitor_thread = None
        self.settings = QSettings('HotspotManager', 'HotspotTool')
        
        # Initialize UI
        self.init_ui()
        self.init_system_tray()
        
        # Start monitoring
        self.start_monitoring()
        
        # Load saved settings
        self.load_settings()
        
        # Check dependencies
        self.check_system_requirements()
    
    def init_ui(self):
        """Initialize the main user interface"""
        self.setWindowTitle("Linux Hotspot Manager")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.create_main_tab()
        self.create_devices_tab()
        self.create_statistics_tab()
        self.create_settings_tab()
        
        # Status bar
        self.statusBar().showMessage("Ready")
        
        # Apply styling
        self.apply_styling()
    
    def create_main_tab(self):
        """Create the main control tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Status group
        status_group = QGroupBox("Hotspot Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("Hotspot is OFF")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; font-weight: bold; color: red;")
        status_layout.addWidget(self.status_label)
        
        layout.addWidget(status_group)
        
        # Configuration group
        config_group = QGroupBox("Configuration")
        config_layout = QGridLayout(config_group)
        
        # SSID
        config_layout.addWidget(QLabel("Network Name (SSID):"), 0, 0)
        self.ssid_edit = QLineEdit()
        self.ssid_edit.setPlaceholderText("Enter network name")
        config_layout.addWidget(self.ssid_edit, 0, 1)
        
        # Password
        config_layout.addWidget(QLabel("Password:"), 1, 0)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Enter password (min 8 chars)")
        config_layout.addWidget(self.password_edit, 1, 1)
        
        # Show password checkbox
        self.show_password_check = QCheckBox("Show Password")
        self.show_password_check.toggled.connect(self.toggle_password_visibility)
        config_layout.addWidget(self.show_password_check, 2, 1)
        
        # Interface selection
        config_layout.addWidget(QLabel("WiFi Interface:"), 3, 0)
        self.interface_combo = QComboBox()
        self.refresh_interfaces()
        config_layout.addWidget(self.interface_combo, 3, 1)
        
        # Internet sharing
        config_layout.addWidget(QLabel("Share Internet From:"), 4, 0)
        self.internet_interface_combo = QComboBox()
        self.internet_interface_combo.addItem("None")
        config_layout.addWidget(self.internet_interface_combo, 4, 1)
        
        layout.addWidget(config_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Hotspot")
        self.start_button.clicked.connect(self.start_hotspot)
        self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("Stop Hotspot")
        self.stop_button.clicked.connect(self.stop_hotspot)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; }")
        button_layout.addWidget(self.stop_button)
        
        self.refresh_button = QPushButton("Refresh Interfaces")
        self.refresh_button.clicked.connect(self.refresh_interfaces)
        button_layout.addWidget(self.refresh_button)
        
        layout.addLayout(button_layout)
        
        # Advanced settings button
        self.advanced_button = QPushButton("Advanced Settings")
        self.advanced_button.clicked.connect(self.show_advanced_settings)
        layout.addWidget(self.advanced_button)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "Main")
    
    def create_devices_tab(self):
        """Create the connected devices tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Devices table
        self.devices_table = QTableWidget()
        self.devices_table.setColumnCount(4)
        self.devices_table.setHorizontalHeaderLabels(["Device Name", "IP Address", "MAC Address", "Status"])
        layout.addWidget(self.devices_table)
        
        # Device control buttons
        button_layout = QHBoxLayout()
        
        self.refresh_devices_button = QPushButton("Refresh")
        self.refresh_devices_button.clicked.connect(self.refresh_devices)
        button_layout.addWidget(self.refresh_devices_button)
        
        self.kick_device_button = QPushButton("Disconnect Selected")
        self.kick_device_button.clicked.connect(self.kick_selected_device)
        self.kick_device_button.setEnabled(False)
        button_layout.addWidget(self.kick_device_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        self.tab_widget.addTab(tab, "Connected Devices")
    
    def create_statistics_tab(self):
        """Create the statistics tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Data usage group
        usage_group = QGroupBox("Data Usage")
        usage_layout = QGridLayout(usage_group)
        
        usage_layout.addWidget(QLabel("Data Sent:"), 0, 0)
        self.data_sent_label = QLabel("0 MB")
        usage_layout.addWidget(self.data_sent_label, 0, 1)
        
        usage_layout.addWidget(QLabel("Data Received:"), 1, 0)
        self.data_received_label = QLabel("0 MB")
        usage_layout.addWidget(self.data_received_label, 1, 1)
        
        usage_layout.addWidget(QLabel("Total Data:"), 2, 0)
        self.total_data_label = QLabel("0 MB")
        usage_layout.addWidget(self.total_data_label, 2, 1)
        
        layout.addWidget(usage_group)
        
        # Connection info group
        info_group = QGroupBox("Connection Information")
        info_layout = QGridLayout(info_group)
        
        info_layout.addWidget(QLabel("Connected Devices:"), 0, 0)
        self.connected_count_label = QLabel("0")
        info_layout.addWidget(self.connected_count_label, 0, 1)
        
        info_layout.addWidget(QLabel("Uptime:"), 1, 0)
        self.uptime_label = QLabel("00:00:00")
        info_layout.addWidget(self.uptime_label, 1, 1)
        
        layout.addWidget(info_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "Statistics")
    
    def create_settings_tab(self):
        """Create the settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # General settings group
        general_group = QGroupBox("General Settings")
        general_layout = QFormLayout(general_group)
        
        # Auto-start
        self.autostart_check = QCheckBox()
        general_layout.addRow("Start with system:", self.autostart_check)
        
        # Minimize to tray
        self.minimize_tray_check = QCheckBox()
        general_layout.addRow("Minimize to system tray:", self.minimize_tray_check)
        
        # Save logs
        self.save_logs_check = QCheckBox()
        general_layout.addRow("Save connection logs:", self.save_logs_check)
        
        layout.addWidget(general_group)
        
        # Security settings group
        security_group = QGroupBox("Security Settings")
        security_layout = QFormLayout(security_group)
        
        # MAC filtering
        self.mac_filter_check = QCheckBox()
        security_layout.addRow("Enable MAC filtering:", self.mac_filter_check)
        
        # Access control
        self.access_control_check = QCheckBox()
        security_layout.addRow("Enable access control:", self.access_control_check)
        
        layout.addWidget(security_group)
        
        # Apply settings button
        apply_button = QPushButton("Apply Settings")
        apply_button.clicked.connect(self.apply_settings)
        layout.addWidget(apply_button)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "Settings")
    
    def init_system_tray(self):
        """Initialize system tray icon"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            
            # Create tray menu
            tray_menu = QMenu()
            
            show_action = QAction("Show", self)
            show_action.triggered.connect(self.show)
            tray_menu.addAction(show_action)
            
            tray_menu.addSeparator()
            
            start_action = QAction("Start Hotspot", self)
            start_action.triggered.connect(self.start_hotspot)
            tray_menu.addAction(start_action)
            
            stop_action = QAction("Stop Hotspot", self)
            stop_action.triggered.connect(self.stop_hotspot)
            tray_menu.addAction(stop_action)
            
            tray_menu.addSeparator()
            
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self.close)
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.show()
    
    def apply_styling(self):
        """Apply modern styling to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            
            QPushButton {
                background-color: #4CAF50;
                border: none;
                color: white;
                padding: 8px 16px;
                text-align: center;
                font-size: 14px;
                border-radius: 4px;
            }
            
            QPushButton:hover {
                background-color: #45a049;
            }
            
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            
            QLineEdit {
                border: 2px solid #ddd;
                border-radius: 4px;
                padding: 5px;
                font-size: 14px;
            }
            
            QLineEdit:focus {
                border-color: #4CAF50;
            }
            
            QComboBox {
                border: 2px solid #ddd;
                border-radius: 4px;
                padding: 5px;
                font-size: 14px;
            }
            
            QTableWidget {
                gridline-color: #ddd;
                background-color: white;
                alternate-background-color: #f9f9f9;
            }
            
            QTableWidget::item {
                padding: 5px;
            }
            
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
            
            QTabBar::tab {
                background-color: #e0e0e0;
                padding: 8px 16px;
                margin-right: 2px;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #4CAF50;
            }
        """)
    
    def check_system_requirements(self):
        """Check if system has required dependencies"""
        success, missing = self.hotspot_manager.check_dependencies()
        
        if not success:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Missing Dependencies")
            msg.setText("Some required tools are missing:")
            msg.setDetailedText("Missing tools:\n" + "\n".join(missing) + 
                              "\n\nPlease install them using your package manager.")
            msg.exec_()
    
    def refresh_interfaces(self):
        """Refresh available network interfaces"""
        # WiFi interfaces
        wifi_interfaces = NetworkInterface.get_wireless_interfaces()
        self.interface_combo.clear()
        self.interface_combo.addItems(wifi_interfaces)
        
        # Internet interfaces
        ethernet_interfaces = NetworkInterface.get_ethernet_interfaces()
        all_interfaces = wifi_interfaces + ethernet_interfaces
        
        self.internet_interface_combo.clear()
        self.internet_interface_combo.addItem("None")
        self.internet_interface_combo.addItems(all