#!/usr/bin/env python3
# hotterspot_daemon.py - Headless service for HotterSpot

import sys
import os
import signal
import time
import argparse
import threading

# Path setup for libs (assuming daemon script is in INSTALL_DIR, and libs in INSTALL_DIR/lib)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(SCRIPT_DIR, 'lib')
if os.path.isdir(LIB_DIR):
    sys.path.insert(0, LIB_DIR)

from production_logger import get_logger
from config_manager import ConfigManager
from hotspot_manager import HotspotManager
from firewall_manager import FirewallManager
from captive_portal import CaptivePortal
from user_manager import UserManager

stop_event = threading.Event()
logger = None

class HeadlessApplication:
    def __init__(self, config_manager_instance, logger_instance):
        self.logger = logger_instance
        self.config_manager = config_manager_instance

        # Correctly pass config_manager to other managers
        # Ensure FirewallManager is initialized before HotspotManager if it's a dependency for it
        self.firewall_manager = FirewallManager(self.config_manager, logger=self.logger) # Added logger
        self.hotspot_manager = HotspotManager(self.config_manager, self.firewall_manager, logger=self.logger) # Added logger and firewall_manager

        # Ensure UserManager uses an absolute path if needed by daemon context.
        # ConfigManager.get_config() should provide absolute paths or resolve them.
        db_path_user_manager = self.config_manager.get_config().get('user_database_path')
        if not db_path_user_manager: # Fallback if not in config
            db_path_user_manager = os.path.join(self.config_manager.config_base_dir, "users.db")
            self.logger.warning(f"User database path not in config, defaulting to: {db_path_user_manager}")

        self.user_manager = UserManager(db_path=db_path_user_manager, logger=self.logger) # Added logger

        self.captive_portal = CaptivePortal(self.config_manager, self.user_manager, self.firewall_manager, logger=self.logger) # Added logger

        # Initialize other monitors if they are to run in daemon mode
        # self.network_monitor = NetworkMonitor(logger=self.logger)
        # self.system_monitor = SystemMonitor(logger=self.logger)
        # self.status_logger = StatusLogger(self.config_manager, logger=self.logger)


    def start(self):
        self.logger.info("HeadlessApplication: Starting services...")
        main_cfg = self.config_manager.get_config()
        system_cfg = self.config_manager.get_system_config() # System config might hold captive portal settings

        hotspot_ssid = main_cfg.get('hotspot_ssid') # Corrected key
        hotspot_password = main_cfg.get('hotspot_password') # Corrected key
        hotspot_interface = main_cfg.get('hotspot_interface') # Corrected key

        if main_cfg.get('auto_start_on_daemon_launch', False):
            self.logger.info(f"Attempting to auto-start hotspot: {hotspot_ssid} on {hotspot_interface}")

            if not all([hotspot_ssid, hotspot_password, hotspot_interface]):
                self.logger.error("SSID, password, or interface not configured. Cannot auto-start hotspot.")
                return

            internet_sharing_iface = main_cfg.get('internet_sharing_source_interface') # Corrected key
            success_hotspot = self.hotspot_manager.create_hotspot(
                hotspot_ssid, hotspot_password, hotspot_interface, internet_sharing_source_iface=internet_sharing_iface
            )
            if success_hotspot:
                self.logger.info(f"Hotspot '{hotspot_ssid}' started successfully by daemon.")

                cp_enabled = self.config_manager.get_config().get('captive_portal_enabled', False) # Get from main_cfg
                if cp_enabled:
                    # Captive portal host/port should ideally come from main_cfg or have sensible defaults in CaptivePortal itself
                    cp_listen_host = self.config_manager.get_config().get('captive_portal_host', '0.0.0.0')
                    cp_port = self.config_manager.get_config().get('captive_portal_port', 8080)

                    if self.captive_portal.start_portal(host=cp_listen_host, port=cp_port):
                       self.logger.info(f"Captive portal started on {cp_listen_host}:{cp_port}.")
                    else:
                       self.logger.error("Captive portal failed to start in daemon mode.")
            else:
                self.logger.error(f"Hotspot '{hotspot_ssid}' failed to start in daemon mode.")
        else:
            self.logger.info("Hotspot auto-start not configured for daemon mode.")
        # Example: if hasattr(self, 'status_logger'): self.status_logger.start_monitoring()

    def stop(self):
        self.logger.info("HeadlessApplication: Stopping services...")
        if hasattr(self, 'captive_portal') and self.captive_portal.is_running(): # Check if running
            self.captive_portal.stop_portal()
            self.logger.info("Captive portal stopped.")
        if hasattr(self, 'hotspot_manager') and self.hotspot_manager.is_hotspot_active(): # Check if active
            self.hotspot_manager.stop_hotspot()
            self.logger.info("Hotspot stopped by daemon.")
        # Example: if hasattr(self, 'status_logger') and self.status_logger.monitoring: self.status_logger.stop_monitoring()
        self.logger.info("HeadlessApplication: Services stopped.")

def signal_handler_daemon(signum, frame):
    global logger, stop_event
    if logger:
        logger.info(f"HotterSpot Daemon received signal {signum}, initiating shutdown...")
    else:
        print(f"HotterSpot Daemon (pre-log) received signal {signum}, initiating shutdown...")
    stop_event.set()

def main_daemon():
    global logger, stop_event

    # Initialize logger first using its default path, update if config changes it
    # This path should be writable by the user running the daemon (e.g. root)
    # Default log path for daemon could be /var/log/hotterspot/daemon.log
    # For now, using production_logger's default.
    logger = get_logger(logger_name="HotterSpotDaemon")
    logger.info("HotterSpot daemon service starting up...")

    # Explicitly set the base directory for configuration files.
    # Systemd service should define WorkingDirectory, but being explicit is safer.
    config_base_dir = "/etc/hotspot-manager"
    # ConfigManager expects the path to the directory containing 'hotspot_config.json', etc.
    # This path should be 'hotspot_config' within config_base_dir as per setup_script.sh
    # So, config_dir argument to ConfigManager should be this full path.
    # The ConfigManager class itself has config_base_dir and then config_dir (e.g. hotspot_config)
    # If ConfigManager's default config_base_dir is /etc/hotspot-manager, then this is fine.
    # Let's assume ConfigManager will correctly find /etc/hotspot-manager/hotspot_config/hotspot_config.json etc.
    # Or, more robustly:
    # main_config_path = os.path.join(config_base_dir, "hotspot_config", "hotspot_config.json")
    # system_config_path = os.path.join(config_base_dir, "hotspot_config", "system_config.json")
    # config_manager_instance = ConfigManager(main_config_file=main_config_path, system_config_file=system_config_path, logger=logger)

    # Simpler: ConfigManager's constructor takes config_dir which is the *parent* of hotspot_config.json
    # So if files are /etc/hotspot-manager/hotspot_config.json, then config_dir="/etc/hotspot-manager"
    # But the setup script creates /etc/hotspot-manager/hotspot_config/hotspot_config.json.
    # So the actual config_dir to pass to ConfigManager should be "/etc/hotspot-manager/hotspot_config"

    effective_config_dir = os.path.join(config_base_dir, "hotspot_config")
    config_manager_instance = ConfigManager(config_dir=effective_config_dir, logger=logger)

    try:
        config_manager_instance.load_config() # Combined load
    except Exception as e:
        logger.critical(f"Failed to load configuration from {effective_config_dir}: {e}. Daemon cannot start.")
        sys.exit(1)

    # Update logger path if specified in loaded config
    log_file_path = config_manager_instance.get_config().get('log_file_path', logger.handlers[0].baseFilename if logger.handlers else None)
    if log_file_path and logger.handlers and logger.handlers[0].baseFilename != log_file_path:
        logger.info(f"Reconfiguring logger to use path from config: {log_file_path}")
        # This is a simplified way; proper logger reconfiguration might involve removing old handlers.
        # For now, assume get_logger handles this or use a new instance.
        logger = get_logger(logger_name="HotterSpotDaemon", log_file_path=log_file_path,
                            log_level_str=config_manager_instance.get_config().get('log_level','INFO'))
        config_manager_instance.logger = logger # Update CM's logger instance

    app = HeadlessApplication(config_manager_instance, logger)
    app.start()

    signal.signal(signal.SIGINT, signal_handler_daemon)
    signal.signal(signal.SIGTERM, signal_handler_daemon)

    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=30)
    finally:
        logger.info("Daemon main loop ending. Cleaning up...")
        app.stop()
        logger.info("HotterSpot daemon shut down gracefully.")

if __name__ == "__main__":
    # Ensure script is run with root privileges for daemon operations
    if os.geteuid() != 0:
        print("HotterSpot Daemon requires root privileges to run.", file=sys.stderr)
        # Logger might not be initialized here if it needs root for log path
        if logger: logger.error("Daemon started without root privileges.")
        sys.exit(1)
    main_daemon()
