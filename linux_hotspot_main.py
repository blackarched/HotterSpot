#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HotterSpot: Comprehensive Linux Hotspot Management Tool
"""

import sys
import os
import subprocess
import threading
import time
import json
import re
import signal
import argparse

try:
    from PyQt5.QtCore import (Qt, QTimer, QThread, pyqtSignal, QSettings, QSize, QPoint, QProcess, QMetaObject)
    from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                                 QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit, QGroupBox,
                                 QCheckBox, QTabWidget, QTableWidget, QTableWidgetItem,
                                 QMessageBox, QSystemTrayIcon, QMenu, QAction, QSizePolicy,
                                 QGridLayout, QFormLayout, QDialog, QDialogButtonBox,
                                 QProgressDialog, QStyle, qApp)
    from PyQt5.QtGui import QIcon, QFont, QPalette, QColor
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # Add dummy classes for headless mode if PyQt5 is not available
    class QMainWindow: pass
    class QApplication: pass
    class QWidget: pass
    # ... any other PyQt5 classes that might be referenced in type hints or shared code paths

from production_logger import get_logger, log_info, log_error, log_warning, log_debug, log_exception
from config_manager import ConfigManager
from hotspot_manager import HotspotManager
from firewall_manager import FirewallManager
from user_manager import UserManager
from captive_portal import CaptivePortal
from bandwidth_manager import BandwidthManager
from network_monitor import NetworkMonitor
from system_monitor import SystemMonitor
from status_logger import StatusLogger
from input_validator import get_validator, ValidationError
from service_manager import ServiceManager # For controlling other services or potentially self

APP_NAME = "HotterSpot"
MAIN_SERVICE_NAME = "hotterspot" # If we need to interact with our own systemd service

# Global stop event for daemon mode
daemon_stop_event = threading.Event()

class HeadlessApplication:
    """
    Manages HotterSpot in daemon (headless) mode.
    """
    def __init__(self, config_manager, logger):
        self.config_manager = config_manager
        self.logger = logger
        log_info("Initializing HeadlessApplication...", logger=self.logger)

        self.firewall_manager = FirewallManager(self.config_manager, logger=self.logger)
        self.hotspot_manager = HotspotManager(self.config_manager, self.firewall_manager, logger=self.logger)
        # UserManager might be needed if Captive Portal uses it directly for auth beyond MAC
        self.user_manager = UserManager(db_path=self.config_manager.get_config().get('user_database_path'), logger=self.logger)
        self.captive_portal = CaptivePortal(self.config_manager, self.user_manager, self.firewall_manager, logger=self.logger)

        self.network_monitor = NetworkMonitor(logger=self.logger)
        self.system_monitor = SystemMonitor(logger=self.logger)
        # StatusLogger might be less relevant for daemon if not writing to a GUI/specific status file
        # self.status_logger = StatusLogger(config_manager, logger=self.logger)

        self.auto_start_hotspot = self.config_manager.get_config().get('auto_start_hotspot_daemon', False)
        self.captive_portal_enabled = self.config_manager.get_config().get('captive_portal_enabled', False)

    def start(self):
        log_info("Starting HotterSpot in daemon mode...", logger=self.logger)
        try:
            self.config_manager.load_config() # Ensure latest config is loaded
        except Exception as e:
            log_error(f"Daemon: Failed to load configuration: {e}", logger=self.logger)
            return False # Cannot start without config

        if self.auto_start_hotspot:
            log_info("Daemon: Auto-starting hotspot...", logger=self.logger)
            try:
                # HotspotManager expects these, get from config
                main_config = self.config_manager.get_config()
                ssid = main_config.get('hotspot_ssid', 'HotterSpot')
                password = main_config.get('hotspot_password', 'password123')
                interface = main_config.get('hotspot_interface')
                if not interface: # Try to autodetect if not set
                    # This needs to call the new hotspot_manager's method
                    interfaces = self.hotspot_manager.get_available_interfaces() # Corrected
                    interface = interfaces.get('wireless', [None])[0] if interfaces.get('wireless') else None

                if not interface:
                    log_error("Daemon: No suitable wireless interface found or configured for auto-start.", logger=self.logger)
                    return False

                self.hotspot_manager.create_hotspot(ssid, password, interface)
                log_info(f"Daemon: Hotspot '{ssid}' initiated on interface '{interface}'.", logger=self.logger)

                if self.captive_portal_enabled:
                    log_info("Daemon: Starting captive portal...", logger=self.logger)
                    self.captive_portal.start_portal()
                else:
                    log_info("Daemon: Captive portal is disabled in configuration.", logger=self.logger)

            except Exception as e:
                log_exception(f"Daemon: Error auto-starting hotspot: {e}", logger=self.logger)
                return False
        else:
            log_info("Daemon: Hotspot auto-start is disabled in configuration.", logger=self.logger)

        # Start background monitoring services
        # self.network_monitor.start_monitoring() # If needed
        # self.system_monitor.start_monitoring() # If needed
        # self.status_logger.start() # If needed

        log_info("Daemon: HeadlessApplication started successfully.", logger=self.logger)
        return True

    def stop(self):
        log_info("Stopping HotterSpot daemon mode...", logger=self.logger)
        if self.captive_portal_enabled and self.captive_portal.is_running():
            log_info("Daemon: Stopping captive portal...", logger=self.logger)
            self.captive_portal.stop_portal()

        # Check if hotspot is active using the new hotspot_manager method
        if self.hotspot_manager.is_hotspot_active(): # Corrected to use actual method if available
            log_info("Daemon: Stopping hotspot...", logger=self.logger)
            self.hotspot_manager.stop_hotspot()

        # Stop background monitoring
        # if self.network_monitor.is_monitoring(): self.network_monitor.stop_monitoring()
        # if self.system_monitor.is_monitoring(): self.system_monitor.stop_monitoring()
        # if self.status_logger.is_running(): self.status_logger.stop()
        log_info("Daemon: HeadlessApplication stopped.", logger=self.logger)

    def run_daemon_loop(self):
        log_info("Daemon: Entering main loop. Press Ctrl+C to exit.", logger=self.logger)
        try:
            while not daemon_stop_event.is_set():
                # Perform periodic checks or tasks if necessary
                # Example: status = self.hotspot_manager.get_hotspot_status() # Corrected
                # if self.auto_start_hotspot and status.get('status') != "active":
                #    log_warning("Daemon: Hotspot seems to have gone down, attempting restart...", logger=self.logger)
                #    self.start() # Or a more nuanced restart logic

                daemon_stop_event.wait(timeout=self.config_manager.get_config().get('daemon_loop_interval', 60))
        finally:
            self.stop()

class HotspotGUI(QMainWindow): # This is the single, clean definition
    """Main GUI application"""
    
    def __init__(self):
        if not PYQT5_AVAILABLE:
            print("CRITICAL: HotspotGUI initialized without PyQt5. This should not happen.", file=sys.stderr)
            log_error("CRITICAL: HotspotGUI initialized without PyQt5.")
            super().__init__()
            return

        super().__init__()
        self.logger = get_logger(log_file_path=None)
        log_info("Initializing HotspotGUI...", logger=self.logger)

        self.validator = get_validator()
        self.config_manager = ConfigManager(logger=self.logger)
        try:
            self.config_manager.load_config()
        except Exception as e:
            log_exception("GUI: Error loading initial configuration.", logger=self.logger)
            if QApplication.instance():
                 QMessageBox.critical(self, "Config Error", f"Failed to load configuration: {e}")
            else:
                log_error("GUI: QApplication not instantiated for config error.")

        self.firewall_manager = FirewallManager(self.config_manager, logger=self.logger)
        self.hotspot_manager = HotspotManager(self.config_manager, self.firewall_manager, logger=self.logger)

        user_db_path = self.config_manager.get_config().get('user_database_path', 'hotspot_users.db')
        self.user_manager = UserManager(db_path=user_db_path, logger=self.logger)

        self.captive_portal = CaptivePortal(self.config_manager, self.user_manager, self.firewall_manager, logger=self.logger)
        self.bandwidth_manager = BandwidthManager(logger=self.logger)
        self.network_monitor = NetworkMonitor(logger=self.logger)
        self.system_monitor = SystemMonitor(logger=self.logger)
        self.status_logger = StatusLogger(self.config_manager, logger=self.logger)
        self.service_manager = ServiceManager(logger=self.logger)

        self.is_hotspot_active = False
        self.current_interface = None
        self.advanced_settings: dict = {}

        self.init_ui()
        self.init_system_tray()
        self.load_settings()
        self.start_gui_timers()

    def start_gui_timers(self):
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.timed_updates)
        self.update_timer.start(5000)
        log_info("GUI: Started UI update timer.", logger=self.logger)

    def timed_updates(self):
        if self.is_hotspot_active:
            if hasattr(self, 'refresh_devices_gui'): self.refresh_devices_gui()
            if self.current_interface and hasattr(self, 'network_traffic_label'):
                try: # Placeholder for actual traffic monitoring
                    self.network_traffic_label.setText("Sent: N/A, Received: N/A (Impl Pend)")
                except Exception: # nosec
                    self.network_traffic_label.setText("Error fetching traffic")
        try:
            cpu = self.system_monitor.get_cpu_usage()
            mem = self.system_monitor.get_memory_usage()
            if hasattr(self, 'cpu_usage_label'): self.cpu_usage_label.setText(f"{cpu:.1f}%")
            if hasattr(self, 'memory_usage_label'): self.memory_usage_label.setText(f"{mem.percent:.1f}% (Used: {mem.used//1024**2:.0f}MB)")
        except Exception: # nosec
            if hasattr(self, 'cpu_usage_label'): self.cpu_usage_label.setText("Error")
            if hasattr(self, 'memory_usage_label'): self.memory_usage_label.setText("Error")

    def load_settings(self):
        log_info("GUI: Loading settings into UI components...", logger=self.logger)
        try:
            config = self.config_manager.get_config()

            # Main Tab
            if hasattr(self, 'ssid_input'): self.ssid_input.setText(config.get('hotspot_ssid', 'HotterSpot'))
            if hasattr(self, 'password_input'): self.password_input.setText(config.get('hotspot_password', 'password123'))
            if hasattr(self, 'interface_combo'):
                saved_interface = config.get('hotspot_interface')
                if saved_interface:
                    index = self.interface_combo.findData(saved_interface) # Assumes data is interface name
                    if index != -1: self.interface_combo.setCurrentIndex(index)
            if hasattr(self, 'internet_interface_combo'):
                saved_sharing_iface = config.get('internet_sharing_source_interface')
                if saved_sharing_iface:
                    idx = self.internet_interface_combo.findData(saved_sharing_iface)
                    if idx != -1: self.internet_interface_combo.setCurrentIndex(idx)
                elif self.internet_interface_combo.count() > 0: # Default to "None"
                    none_idx = self.internet_interface_combo.findData(None)
                    if none_idx != -1: self.internet_interface_combo.setCurrentIndex(none_idx)


            # Settings Tab
            if hasattr(self, 'autostart_gui_checkbox'):
                self.autostart_gui_checkbox.setChecked(config.get('gui_auto_start_hotspot_on_launch', False))
            if hasattr(self, 'minimize_tray_check'):
                 self.minimize_tray_check.setChecked(config.get('gui_minimize_to_tray', False))
            if hasattr(self, 'save_logs_check'):
                 self.save_logs_check.setChecked(config.get('save_connection_logs', True))


            if hasattr(self, 'captive_portal_checkbox'):
                cp_enabled = config.get('captive_portal_enabled', False)
                self.captive_portal_checkbox.setChecked(cp_enabled)
                if hasattr(self, 'captive_portal_group'): self.captive_portal_group.setEnabled(cp_enabled)
                if hasattr(self, 'captive_portal_title_input'): self.captive_portal_title_input.setText(config.get('captive_portal_title', 'Welcome to HotterSpot'))
                if hasattr(self, 'captive_portal_welcome_input'): self.captive_portal_welcome_input.setPlainText(config.get('captive_portal_welcome_message', 'Please accept the terms to connect.'))


            if config.get('gui_auto_start_hotspot_on_launch', False) and not self.is_hotspot_active:
                if hasattr(self, 'start_hotspot_gui'): QTimer.singleShot(100, self.start_hotspot_gui)

        except Exception as e:
            log_exception("GUI: Error loading settings into UI", logger=self.logger)
            if QApplication.instance(): # Ensure app exists before showing messagebox
                QMessageBox.warning(self, "Load Settings Error", f"Could not load all settings: {e}")
            else:
                log_error("GUI: QApplication not instantiated, cannot show QMessageBox for Load Settings Error.")

    def init_ui(self):
        """Initialize the main user interface"""
        self.setWindowTitle(f"{APP_NAME} - Control Panel")
        self.setGeometry(100, 100, 800, 600)
        
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.tabs = QTabWidget() # Use self.tabs consistently
        main_layout.addWidget(self.tabs)

        # Create tab content by calling respective methods
        # These methods should exist in the class and build the UI for each tab
        # For example, self.create_main_tab() should populate a QWidget and add it to self.tabs
        self.create_main_tab() # Assumes this method is defined and works
        self.create_devices_tab() # Assumes this method is defined
        # self.create_statistics_tab() # Keep or remove based on new design
        self.create_settings_tab() # Assumes this method is defined

        # From the new structure, you might have these too:
        if hasattr(self, 'create_logs_tab'): self.create_logs_tab()
        if hasattr(self, 'create_system_status_tab'): self.create_system_status_tab()
        
        self.statusBar().showMessage("Ready")
        
        if hasattr(self, 'apply_styling'): # Check if apply_styling method exists
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
        
        self.tabs.addTab(tab, "Settings") # Ensure it's self.tabs (already self.tabs from previous change)

    def apply_gui_settings(self): # Renamed from apply_settings
        """Apply and save settings from the GUI to ConfigManager."""
        log_info("GUI: Applying and saving settings...", logger=self.logger)
        try:
            if hasattr(self, 'autostart_check'):
                self.config_manager.set_config('gui_auto_start_hotspot_on_launch', self.autostart_check.isChecked())
            if hasattr(self, 'minimize_tray_check'):
                self.config_manager.set_config('gui_minimize_to_tray', self.minimize_tray_check.isChecked())
            if hasattr(self, 'save_logs_check'):
                 self.config_manager.set_config('save_connection_logs', self.save_logs_check.isChecked())

            if hasattr(self, 'captive_portal_checkbox') and hasattr(self, 'captive_portal_title_input') and hasattr(self, 'captive_portal_welcome_input'):
                cp_enabled = self.captive_portal_checkbox.isChecked()
                self.config_manager.set_config('captive_portal_enabled', cp_enabled)
                if cp_enabled:
                    self.config_manager.set_config('captive_portal_title', self.captive_portal_title_input.text())
                    self.config_manager.set_config('captive_portal_welcome_message', self.captive_portal_welcome_input.toPlainText())

            # Save internet sharing choice
            if hasattr(self, 'internet_interface_combo') and self.internet_interface_combo is not None:
                sharing_iface = self.internet_interface_combo.currentData()
                self.config_manager.set_config('internet_sharing_source_interface', sharing_iface)


            self.config_manager.save_config()
            if hasattr(self, 'statusBar'): self.statusBar().showMessage("Settings saved successfully.")
            log_info("GUI: Settings saved via ConfigManager.", logger=self.logger)
            if QApplication.instance():
                QMessageBox.information(self, "Settings Saved", "Configuration has been saved.")

            if self.captive_portal.is_running() and hasattr(self, 'captive_portal_checkbox') and self.captive_portal_checkbox.isChecked():
                 if hasattr(self, 'captive_portal_title_input'): self.captive_portal.title = self.captive_portal_title_input.text()
                 if hasattr(self, 'captive_portal_welcome_input'): self.captive_portal.welcome_message = self.captive_portal_welcome_input.toPlainText()

        except ValidationError as ve:
            log_error(f"GUI: Validation error while applying settings: {ve}", logger=self.logger)
            if QApplication.instance(): QMessageBox.warning(self, "Settings Validation Error", str(ve))
            if hasattr(self, 'statusBar'): self.statusBar().showMessage("Error saving settings: Validation failed.")
        except Exception as e:
            log_exception("GUI: Error applying settings", logger=self.logger)
            if QApplication.instance(): QMessageBox.critical(self, "Settings Error", f"Failed to save settings: {e}")
            if hasattr(self, 'statusBar'): self.statusBar().showMessage("Failed to save settings.")

    def start_hotspot_gui(self):
        if not (hasattr(self, 'ssid_edit') and hasattr(self, 'password_edit') and hasattr(self, 'interface_combo')):
            log_error("GUI: start_hotspot_gui called, but UI elements are missing.", logger=self.logger)
            if QApplication.instance(): QMessageBox.critical(self, "UI Error", "Cannot start hotspot: UI components not found.")
            return

        ssid = self.ssid_edit.text()
        password = self.password_edit.text()
        interface = self.interface_combo.currentData()

        try:
            self.validator.validate('ssid', ssid)
            self.validator.validate('password', password)
            if not interface or "No suitable" in str(interface) or "Error loading" in str(interface) :
                raise ValidationError("A valid network interface must be selected.")
        except ValidationError as e:
            if QApplication.instance(): QMessageBox.warning(self, "Input Error", str(e))
            log_warning(f"GUI: Hotspot start validation error: {e}", logger=self.logger)
            return

        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(False)
            self.start_button.setText("Starting...")
        if hasattr(self, 'statusBar'): self.statusBar().showMessage(f"Attempting to start hotspot on {interface}...")

        self.hotspot_thread = threading.Thread(target=self._start_hotspot_thread_func,
                                               args=(ssid, password, interface), daemon=True)
        self.hotspot_thread.start()

    def _start_hotspot_thread_func(self, ssid, password, interface):
        try:
            internet_sharing_source = None
            if hasattr(self, 'internet_interface_combo') and self.internet_interface_combo is not None:
                internet_sharing_source = self.internet_interface_combo.currentData()
                # Internet sharing source is saved by apply_gui_settings if changed there,
                # or can be saved here if direct start is desired without explicit apply.
                # For now, assume it's already configured if needed.

            self.hotspot_manager.create_hotspot(ssid, password, interface, internet_sharing_source_iface=internet_sharing_source)

            if self.config_manager.get_config().get('captive_portal_enabled', False):
                log_info("GUI: Starting captive portal after hotspot creation...", logger=self.logger)
                self.captive_portal.start_portal()

            self.is_hotspot_active = True
            self.current_interface = interface

            QMetaObject.invokeMethod(self, "_update_gui_post_start", Qt.QueuedConnection,
                                     pyqtSignal(str, str).emit(f"Hotspot '{ssid}' is Active on {interface}", "green"))
        except Exception as e:
            log_exception("GUI: Failed to start hotspot", logger=self.logger)
            self.is_hotspot_active = False
            QMetaObject.invokeMethod(self, "_update_gui_post_start_failure", Qt.QueuedConnection,
                                     pyqtSignal(str).emit(f"Error: {str(e)}"))

    def _update_gui_post_start(self, status_message, color_name):
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_message)
            self.status_label.setStyleSheet(f"color: {color_name}; font-weight: bold;")

        if hasattr(self, 'start_button'): self.start_button.setEnabled(False)
        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(True)
            self.stop_button.setText("Stop Hotspot")

        if hasattr(self, 'statusBar'): self.statusBar().showMessage(status_message)

        if hasattr(self, 'ssid_edit'): self.ssid_edit.setEnabled(False)
        if hasattr(self, 'password_edit'): self.password_edit.setEnabled(False)
        if hasattr(self, 'interface_combo'): self.interface_combo.setEnabled(False)
        if hasattr(self, 'refresh_button'): self.refresh_button.setEnabled(False)
        if hasattr(self, 'internet_interface_combo'): self.internet_interface_combo.setEnabled(False)
        if hasattr(self, 'refresh_devices_gui'): self.refresh_devices_gui()

    def _update_gui_post_start_failure(self, error_message):
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"Hotspot Status: Failed")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(True)
            self.start_button.setText("Start Hotspot")
        if hasattr(self, 'stop_button'): self.stop_button.setEnabled(False)

        if hasattr(self, 'statusBar'): self.statusBar().showMessage(f"Failed to start hotspot: {error_message}")
        if QApplication.instance(): QMessageBox.critical(self, "Hotspot Error", f"Failed to start hotspot: {error_message}")

        if hasattr(self, 'ssid_edit'): self.ssid_edit.setEnabled(True)
        if hasattr(self, 'password_edit'): self.password_edit.setEnabled(True)
        if hasattr(self, 'interface_combo'): self.interface_combo.setEnabled(True)
        if hasattr(self, 'refresh_button'): self.refresh_button.setEnabled(True)
        if hasattr(self, 'internet_interface_combo'): self.internet_interface_combo.setEnabled(True)

    def stop_hotspot_gui(self):
        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stopping...")
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("Attempting to stop hotspot...")

        self.hotspot_thread = threading.Thread(target=self._stop_hotspot_thread_func, daemon=True)
        self.hotspot_thread.start()

    def _stop_hotspot_thread_func(self):
        try:
            if self.captive_portal.is_running():
                log_info("GUI: Stopping captive portal...", logger=self.logger)
                self.captive_portal.stop_portal()

            self.hotspot_manager.stop_hotspot() # From the new HotspotManager class
            self.is_hotspot_active = False
            self.current_interface = None
            QMetaObject.invokeMethod(self, "_update_gui_post_stop", Qt.QueuedConnection,
                                     pyqtSignal(str, str).emit("Hotspot Status: Inactive", "red"))
        except Exception as e:
            log_exception("GUI: Failed to stop hotspot", logger=self.logger)
            QMetaObject.invokeMethod(self, "_update_gui_post_stop_failure", Qt.QueuedConnection,
                                     pyqtSignal(str).emit(f"Error stopping hotspot: {str(e)}"))

    def _update_gui_post_stop(self, status_message, color_name):
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_message)
            self.status_label.setStyleSheet(f"color: {color_name}; font-weight: bold;")

        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(True)
            self.start_button.setText("Start Hotspot")
        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stop Hotspot")
            
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("Hotspot stopped.")

        if hasattr(self, 'ssid_edit'): self.ssid_edit.setEnabled(True)
        if hasattr(self, 'password_edit'): self.password_edit.setEnabled(True)
        if hasattr(self, 'interface_combo'): self.interface_combo.setEnabled(True)
        if hasattr(self, 'refresh_button'): self.refresh_button.setEnabled(True)
        if hasattr(self, 'internet_interface_combo'): self.internet_interface_combo.setEnabled(True)
        if hasattr(self, 'devices_table'): self.devices_table.setRowCount(0)

    def _update_gui_post_stop_failure(self, error_message):
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"Hotspot Status: Error Stopping")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")

        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(True)
            self.stop_button.setText("Stop Hotspot")
        if hasattr(self, 'statusBar'): self.statusBar().showMessage(error_message)
        if QApplication.instance(): QMessageBox.critical(self, "Hotspot Error", error_message)

    def refresh_devices_gui(self):
        if not (hasattr(self, 'devices_table') and self.devices_table):
             log_warning("GUI: refresh_devices_gui called but devices_table is missing.", logger=self.logger)
             return

        if not self.is_hotspot_active:
            self.devices_table.setRowCount(0)
            if hasattr(self, 'connected_count_label'): self.connected_count_label.setText("0") # Assuming this label exists
            return

        try:
            # current_interface should be valid if hotspot is active
            devices = self.hotspot_manager.get_connected_devices(self.current_interface if self.current_interface else "")
            self.devices_table.setRowCount(len(devices))

            # These headers should match what's set in create_devices_tab
            # ["IP Address", "MAC Address", "Name", "Actions", "Data Usage"]
            for row, device in enumerate(devices):
                ip = device.get('ip', 'N/A')
                mac = device.get('mac', 'N/A')
                name = device.get('name', '')
                if not name or name == mac or name == ip:
                    name = 'Unknown'

                self.devices_table.setItem(row, 0, QTableWidgetItem(ip))
                self.devices_table.setItem(row, 1, QTableWidgetItem(mac))
                self.devices_table.setItem(row, 2, QTableWidgetItem(name))

                # Column 3: Actions (e.g., Block Button)
                # This column will be populated with a widget in create_devices_tab.
                # If not, self.devices_table.setItem(row, 3, QTableWidgetItem("N/A"))

                # Column 4: Data Usage
                if self.devices_table.columnCount() > 4 : # Check if column exists
                     self.devices_table.setItem(row, 4, QTableWidgetItem(device.get('data_usage', 'N/A')))


            if hasattr(self, 'connected_count_label'): self.connected_count_label.setText(str(len(devices)))
            # Kick button enablement depends on selection, handled by table's itemSelectionChanged signal if any
            if hasattr(self, 'kick_device_button'): self.kick_device_button.setEnabled(len(devices) > 0)


        except Exception as e:
            log_exception("GUI: Error refreshing device list", logger=self.logger)
            if QApplication.instance(): QMessageBox.warning(self, "Device Error", f"Could not load connected devices: {e}")
            self.devices_table.setRowCount(0)
            if hasattr(self, 'connected_count_label'): self.connected_count_label.setText("0")

    def start_hotspot_gui(self):
        if not (hasattr(self, 'ssid_edit') and hasattr(self, 'password_edit') and hasattr(self, 'interface_combo')):
            log_error("GUI: start_hotspot_gui called, but UI elements are missing.", logger=self.logger)
            if QApplication.instance(): QMessageBox.critical(self, "UI Error", "Cannot start hotspot: UI components not found.")
            return

        ssid = self.ssid_edit.text()
        password = self.password_edit.text()
        interface = self.interface_combo.currentData()

        try:
            self.validator.validate('ssid', ssid)
            self.validator.validate('password', password)
            if not interface or "No suitable" in str(interface) or "Error loading" in str(interface) :
                raise ValidationError("A valid network interface must be selected.")
        except ValidationError as e:
            if QApplication.instance(): QMessageBox.warning(self, "Input Error", str(e))
            log_warning(f"GUI: Hotspot start validation error: {e}", logger=self.logger)
            return

        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(False)
            self.start_button.setText("Starting...")
        if hasattr(self, 'statusBar'): self.statusBar().showMessage(f"Attempting to start hotspot on {interface}...")

        self.hotspot_thread = threading.Thread(target=self._start_hotspot_thread_func,
                                               args=(ssid, password, interface), daemon=True)
        self.hotspot_thread.start()

    def _start_hotspot_thread_func(self, ssid, password, interface):
        try:
            internet_sharing_source = None
            if hasattr(self, 'internet_interface_combo') and self.internet_interface_combo is not None:
                internet_sharing_source = self.internet_interface_combo.currentData()
                # self.config_manager.set_config('internet_sharing_source_interface', internet_sharing_source) # Already saved by apply_gui_settings
                # self.config_manager.save_config()

            self.hotspot_manager.create_hotspot(ssid, password, interface, internet_sharing_source_iface=internet_sharing_source)
            
            if self.config_manager.get_config().get('captive_portal_enabled', False):
                log_info("GUI: Starting captive portal after hotspot creation...", logger=self.logger)
                self.captive_portal.start_portal()

            self.is_hotspot_active = True
            self.current_interface = interface
            
            QMetaObject.invokeMethod(self, "_update_gui_post_start", Qt.QueuedConnection,
                                     pyqtSignal(str, str).emit(f"Hotspot '{ssid}' is Active on {interface}", "green"))
        except Exception as e:
            log_exception("GUI: Failed to start hotspot", logger=self.logger)
            self.is_hotspot_active = False
            QMetaObject.invokeMethod(self, "_update_gui_post_start_failure", Qt.QueuedConnection,
                                     pyqtSignal(str).emit(f"Error: {str(e)}"))

    def _update_gui_post_start(self, status_message, color_name):
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_message)
            self.status_label.setStyleSheet(f"color: {color_name}; font-weight: bold;")

        if hasattr(self, 'start_button'): self.start_button.setEnabled(False)
        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(True)
            self.stop_button.setText("Stop Hotspot")

        if hasattr(self, 'statusBar'): self.statusBar().showMessage(status_message)

        if hasattr(self, 'ssid_edit'): self.ssid_edit.setEnabled(False)
        if hasattr(self, 'password_edit'): self.password_edit.setEnabled(False)
        if hasattr(self, 'interface_combo'): self.interface_combo.setEnabled(False)
        if hasattr(self, 'refresh_button'): self.refresh_button.setEnabled(False)
        if hasattr(self, 'internet_interface_combo'): self.internet_interface_combo.setEnabled(False)
        if hasattr(self, 'refresh_devices_gui'): self.refresh_devices_gui()

    def _update_gui_post_start_failure(self, error_message):
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"Hotspot Status: Failed")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(True)
            self.start_button.setText("Start Hotspot")
        if hasattr(self, 'stop_button'): self.stop_button.setEnabled(False)

        if hasattr(self, 'statusBar'): self.statusBar().showMessage(f"Failed to start hotspot: {error_message}")
        if QApplication.instance(): QMessageBox.critical(self, "Hotspot Error", f"Failed to start hotspot: {error_message}")

        if hasattr(self, 'ssid_edit'): self.ssid_edit.setEnabled(True)
        if hasattr(self, 'password_edit'): self.password_edit.setEnabled(True)
        if hasattr(self, 'interface_combo'): self.interface_combo.setEnabled(True)
        if hasattr(self, 'refresh_button'): self.refresh_button.setEnabled(True)
        if hasattr(self, 'internet_interface_combo'): self.internet_interface_combo.setEnabled(True)

    def stop_hotspot_gui(self):
        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stopping...")
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("Attempting to stop hotspot...")

        self.hotspot_thread = threading.Thread(target=self._stop_hotspot_thread_func, daemon=True)
        self.hotspot_thread.start()

    def _stop_hotspot_thread_func(self):
        try:
            if self.captive_portal.is_running():
                log_info("GUI: Stopping captive portal...", logger=self.logger)
                self.captive_portal.stop_portal()
            
            self.hotspot_manager.stop_hotspot()
            self.is_hotspot_active = False
            self.current_interface = None
            QMetaObject.invokeMethod(self, "_update_gui_post_stop", Qt.QueuedConnection,
                                     pyqtSignal(str, str).emit("Hotspot Status: Inactive", "red"))
        except Exception as e:
            log_exception("GUI: Failed to stop hotspot", logger=self.logger)
            QMetaObject.invokeMethod(self, "_update_gui_post_stop_failure", Qt.QueuedConnection,
                                     pyqtSignal(str).emit(f"Error stopping hotspot: {str(e)}"))

    def _update_gui_post_stop(self, status_message, color_name):
        if hasattr(self, 'status_label'):
            self.status_label.setText(status_message)
            self.status_label.setStyleSheet(f"color: {color_name}; font-weight: bold;")

        if hasattr(self, 'start_button'):
            self.start_button.setEnabled(True)
            self.start_button.setText("Start Hotspot")
        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Stop Hotspot")
            
        if hasattr(self, 'statusBar'): self.statusBar().showMessage("Hotspot stopped.")

        if hasattr(self, 'ssid_edit'): self.ssid_edit.setEnabled(True)
        if hasattr(self, 'password_edit'): self.password_edit.setEnabled(True)
        if hasattr(self, 'interface_combo'): self.interface_combo.setEnabled(True)
        if hasattr(self, 'refresh_button'): self.refresh_button.setEnabled(True)
        if hasattr(self, 'internet_interface_combo'): self.internet_interface_combo.setEnabled(True)
        if hasattr(self, 'devices_table'): self.devices_table.setRowCount(0)

    def _update_gui_post_stop_failure(self, error_message):
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"Hotspot Status: Error Stopping")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")

        if hasattr(self, 'stop_button'):
            self.stop_button.setEnabled(True)
            self.stop_button.setText("Stop Hotspot")
        if hasattr(self, 'statusBar'): self.statusBar().showMessage(error_message)
        if QApplication.instance(): QMessageBox.critical(self, "Hotspot Error", error_message)

    def refresh_devices_gui(self):
        if not (hasattr(self, 'devices_table') and self.devices_table):
             log_warning("GUI: refresh_devices_gui called but devices_table is missing.", logger=self.logger)
             return

        if not self.is_hotspot_active:
            self.devices_table.setRowCount(0)
            if hasattr(self, 'connected_count_label'): self.connected_count_label.setText("0")
            return

        try:
            devices = self.hotspot_manager.get_connected_devices(self.current_interface if self.current_interface else "")
            self.devices_table.setRowCount(len(devices))
            for row, device in enumerate(devices):
                ip = device.get('ip', 'N/A')
                mac = device.get('mac', 'N/A')
                name = device.get('name', '')
                if not name or name == mac or name == ip:
                    name = 'Unknown'

                self.devices_table.setItem(row, 0, QTableWidgetItem(ip))
                self.devices_table.setItem(row, 1, QTableWidgetItem(mac))
                self.devices_table.setItem(row, 2, QTableWidgetItem(name))

                # Column 3 for Actions (placeholder text, actual widget in create_devices_tab)
                # Example: self.devices_table.setItem(row, 3, QTableWidgetItem("Block"))

                # Column 4 for Data Usage - ensure this column exists in create_devices_tab
                if self.devices_table.columnCount() > 4:
                    self.devices_table.setItem(row, 4, QTableWidgetItem(device.get('data_usage', 'N/A')))


            if hasattr(self, 'connected_count_label'): self.connected_count_label.setText(str(len(devices)))
            if hasattr(self, 'kick_device_button'): self.kick_device_button.setEnabled(len(devices) > 0 and bool(self.devices_table.selectedItems()))

        except Exception as e:
            log_exception("GUI: Error refreshing device list", logger=self.logger)
            if QApplication.instance(): QMessageBox.warning(self, "Device Error", f"Could not load connected devices: {e}")
            self.devices_table.setRowCount(0)
            if hasattr(self, 'connected_count_label'): self.connected_count_label.setText("0")

    # This should remove the last duplicated block of stop_hotspot_gui and refresh_devices_gui

    def kick_selected_device(self): # This method is already up-to-date from a previous step
        if not (hasattr(self, 'devices_table') and self.devices_table):
            log_warning("GUI: kick_selected_device called but devices_table is missing.", logger=self.logger)
            return

        selected_items = self.devices_table.selectedItems()
        if not selected_items :
            if QApplication.instance(): QMessageBox.information(self, "No Device Selected", "Please select a device from the table.")
            return

        row_index = selected_items[0].row()
        # MAC Address is in column 1, make sure create_devices_tab sets this up.
        mac_item = self.devices_table.item(row_index, 1)

        if not mac_item or not mac_item.text():
             if QApplication.instance(): QMessageBox.warning(self, "MAC Not Found", "Could not retrieve MAC address for the selected device.")
             return
        mac_address = mac_item.text()

        identifier_item = self.devices_table.item(row_index, 0) # IP/Name is column 0
        device_identifier = identifier_item.text() if identifier_item else mac_address

        reply = QMessageBox.question(self, "Block Device",
                                     f"Are you sure you want to block device '{device_identifier}' ({mac_address})?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                self.firewall_manager.block_mac_address(mac_address)
                log_info(f"GUI: Manually blocked MAC: {mac_address}", logger=self.logger)
                if QApplication.instance(): QMessageBox.information(self, "Device Blocked", f"Device {mac_address} blocked successfully.")
                if hasattr(self, 'refresh_devices_gui'): self.refresh_devices_gui()
            except Exception as e:
                log_exception(f"GUI: Error blocking MAC {mac_address}", logger=self.logger)
                if QApplication.instance(): QMessageBox.critical(self, "Blocking Error", f"Failed to block device: {e}")

    def init_system_tray(self): # This is the new version of init_system_tray
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log_warning("GUI: System tray not available on this system.", logger=self.logger)
            return

        self.tray_icon = QSystemTrayIcon(self)
        try:
            # Standard way to reference package resources is more complex (e.g. via importlib.resources)
            # For simplicity, assuming icon.png is discoverable relative to the script.
            # A better approach would be to use Qt's resource system (qrc files).
            base_dir = os.path.dirname(os.path.abspath(__file__)) # Gets dir of current script
            app_icon_path = os.path.join(base_dir, 'icon.png') # Placeholder for actual icon path or resource name
            
            if not os.path.exists(app_icon_path):
                log_warning(f"Icon not found at {app_icon_path}, attempting theme icon or default.", logger=self.logger)
                # Try to get a generic network icon from theme as a fallback
                app_icon = QIcon.fromTheme("network-wireless", self.style().standardIcon(QStyle.SP_NetworkWirelessEnabled))
                if app_icon.isNull() or app_icon.name() == "network-wireless": # If theme icon not found or generic
                     app_icon = self.style().standardIcon(QStyle.SP_ApplicationIcon) # Ultimate fallback
            else:
                app_icon = QIcon(app_icon_path)
            
            if app_icon.isNull(): # Check if any icon was successfully loaded
                log_error("Setting window icon to a null QIcon. Using default style's application icon.", logger=self.logger)
                app_icon = self.style().standardIcon(QStyle.SP_ApplicationIcon) # Final fallback
            
            self.setWindowIcon(app_icon) # Set for the main window too
            self.tray_icon.setIcon(app_icon)
        except Exception as e:
            log_exception(f"GUI: Failed to load or set icon: {e}", logger=self.logger)
            if hasattr(self, 'style') and callable(self.style): # Ensure self.style() is valid
                 self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ApplicationIcon))

        tray_menu = QMenu(self) # Parent menu to self for proper cleanup

        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_window_and_raise) # showNormal + activateWindow
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        start_gui_action = QAction("Start Hotspot", self)
        if hasattr(self, 'start_hotspot_gui'): start_gui_action.triggered.connect(self.start_hotspot_gui)
        tray_menu.addAction(start_gui_action)

        stop_gui_action = QAction("Stop Hotspot", self)
        if hasattr(self, 'stop_hotspot_gui'): stop_gui_action.triggered.connect(self.stop_hotspot_gui)
        tray_menu.addAction(stop_gui_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit HotterSpot", self) # More specific title
        # Use close_application_logic to bypass QCloseEvent prompt if desired from tray
        if hasattr(self, 'close_application_logic'):
            quit_action.triggered.connect(lambda: self.close_application_logic(from_tray=True))
        else:
            quit_action.triggered.connect(self.close) # Fallback to standard close (will show prompt)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated) # Handle clicks on tray icon
        self.tray_icon.show()
        log_info("GUI: System tray icon initialized and shown.", logger=self.logger)

    def tray_icon_activated(self, reason):
        """Handle tray icon activation (click, double click)."""
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger: # Single or Double click
            self.show_window_and_raise()

    def show_window_and_raise(self):
        """Utility to show, de-minimize, and raise the window."""
        self.showNormal() # De-minimize if minimized
        self.raise_() # Raise to top (platform dependent)
        self.activateWindow() # Bring focus (platform dependent)

    def toggle_password_visibility(self, checked): # Assuming self.password_edit exists
        if hasattr(self, 'password_edit'):
            self.password_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        else:
            log_warning("GUI: toggle_password_visibility called but password_edit not found.", logger=self.logger)

    def show_advanced_settings(self): # Placeholder, already updated
        log_info("GUI: 'Advanced Settings' button clicked. Placeholder action.", logger=self.logger)
        if QApplication.instance():
            QMessageBox.information(self, "Advanced Settings",
                                    "Advanced configuration is managed via the main settings tab "
                                    "and the configuration file directly for now.")
    
    def apply_styling(self):
        """Apply modern styling to the application"""
        # Content of apply_styling is kept from original for now.
        # Review if UI elements change significantly.
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

    def refresh_interfaces(self):
        """Refresh available network interfaces using HotspotManager."""
        if not hasattr(self, 'interface_combo') or self.interface_combo is None:
            log_warning("GUI: refresh_interfaces called but interface_combo is None or missing.", logger=self.logger)
            return

        self.interface_combo.clear()
        selected_index = 0
        
        try:
            interfaces_data = self.hotspot_manager.get_available_interfaces()
            all_ifaces_display = []
            all_ifaces_data = []

            if interfaces_data.get('wireless'):
                for iface in interfaces_data['wireless']:
                    all_ifaces_display.append(f"{iface} (Wireless)")
                    all_ifaces_data.append(iface)
            if interfaces_data.get('ethernet'):
                for iface in interfaces_data['ethernet']:
                     all_ifaces_display.append(f"{iface} (Ethernet - Advanced)")
                     all_ifaces_data.append(iface)

            if not all_ifaces_data:
                self.interface_combo.addItem("No suitable interfaces found")
                self.interface_combo.setEnabled(False)
                if hasattr(self, 'start_button'): self.start_button.setEnabled(False)
            else:
                current_config_interface = self.config_manager.get_config().get('hotspot_interface')
                for i, iface_data in enumerate(all_ifaces_data):
                    self.interface_combo.addItem(all_ifaces_display[i], iface_data)
                    if iface_data == current_config_interface:
                        selected_index = i
                self.interface_combo.setCurrentIndex(selected_index)
                self.interface_combo.setEnabled(True)
                if hasattr(self, 'start_button'): self.start_button.setEnabled(not self.is_hotspot_active)
            log_info(f"GUI: Refreshed interfaces. Found: {all_ifaces_data}", logger=self.logger)

        except Exception as e:
            log_exception("GUI: Error refreshing interfaces", logger=self.logger)
            if QApplication.instance(): QMessageBox.warning(self, "Interface Error", f"Could not load network interfaces: {e}")
            self.interface_combo.addItem("Error loading interfaces")
            self.interface_combo.setEnabled(False)
            if hasattr(self, 'start_button'): self.start_button.setEnabled(False)

        if hasattr(self, 'internet_interface_combo'):
            self.internet_interface_combo.clear()
            self.internet_interface_combo.addItem("None (Do Not Share)", None)
            try:
                import netifaces # Keep import local if only used here
                sys_interfaces = netifaces.interfaces()
                current_hotspot_iface_data = self.interface_combo.currentData()

                for iface_name in sys_interfaces:
                    if current_hotspot_iface_data and iface_name == current_hotspot_iface_data:
                        continue
                    self.internet_interface_combo.addItem(iface_name, iface_name)

                saved_inet_iface = self.config_manager.get_config().get('internet_sharing_source_interface')
                if saved_inet_iface:
                    idx = self.internet_interface_combo.findData(saved_inet_iface)
                    if idx != -1: self.internet_interface_combo.setCurrentIndex(idx)
                elif self.internet_interface_combo.count() > 0:
                    none_idx = self.internet_interface_combo.findData(None)
                    if none_idx != -1: self.internet_interface_combo.setCurrentIndex(none_idx)
            except Exception as e:
                log_warning(f"GUI: Could not populate internet_interface_combo: {e}", logger=self.logger)