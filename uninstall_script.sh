#!/bin/bash

# Linux Hotspot Manager - Uninstall Script
# This script removes the hotspot manager and cleans up system changes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation paths and names
INSTALL_DIR="/opt/hotspot-manager" # This is where HotterSpot and its venv are installed
DESKTOP_FILE="/usr/share/applications/hotterspot.desktop" # Changed name
BIN_LINK="/usr/local/bin/hotterspot" # Changed name
SERVICE_NAME="hotterspot" # Consistent service name, changed from hotspot-manager
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
CONFIG_DIR_BASE="/etc/hotspot-manager" # Main config folder
# CONFIG_DIR_JSON="${CONFIG_DIR_BASE}/hotspot_config" # Specific subdir for JSONs - not directly used for removal, base is enough
LOG_DIR_APP="/var/log/hotspot-manager" # Log directory, not just a single file
LOGROTATE_FILE="/etc/logrotate.d/hotterspot" # Changed name
NETWORKMANAGER_CONF="/etc/NetworkManager/conf.d/hotspot-manager.conf" # Name was hotspot-manager.conf
# Correcting NETWORKMANAGER_CONF to align with setup_script.sh if it was changed there.
# Assuming setup script used 'hotspot-manager.conf' as per original, if it's 'hotterspot.conf', this needs to match.
# For now, keeping 'hotspot-manager.conf' as the setup script was not explicitly asked to change this specific file name.
# If setup_script.sh *did* change it to hotterspot.conf, this variable should be:
# NETWORKMANAGER_CONF="/etc/NetworkManager/conf.d/hotterspot.conf"
NMCLI_CONNECTION_NAME="HotterSpot" # Name used by nmcli to create the hotspot connection. Make sure this is consistent with setup.

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Stop and disable service
stop_service() {
    log "Stopping and disabling ${SERVICE_NAME} service..."
    
    if systemctl is-active --quiet "${SERVICE_NAME}.service" &>/dev/null; then
        log "Stopping ${SERVICE_NAME} service..."
        systemctl stop "${SERVICE_NAME}.service" || warn "Failed to stop ${SERVICE_NAME} service. It might have already been stopped."
    else
        log "${SERVICE_NAME} service is not active."
    fi
    
    if systemctl is-enabled --quiet "${SERVICE_NAME}.service" &>/dev/null; then
        log "Disabling ${SERVICE_NAME} service..."
        systemctl disable "${SERVICE_NAME}.service" || warn "Failed to disable ${SERVICE_NAME} service."
    else
        log "${SERVICE_NAME} service is not enabled."
    fi
    success "Service stop and disable actions attempted."
}

# Clean up any running hotspots
cleanup_hotspots() {
    log "Cleaning up any running hotspots (NetworkManager connections)..."
    
    # Stop any NetworkManager hotspot connections matching NMCLI_CONNECTION_NAME
    # List all connections, filter by name, then process
    nmcli -g NAME,TYPE connection show | grep ":802-11-wireless$" | cut -d: -f1 | while read -r conn_name; do
        if [ "$conn_name" == "$NMCLI_CONNECTION_NAME" ]; then
            log "Found active hotspot connection: $conn_name"
            log "Attempting to bring down connection: $conn_name"
            nmcli connection down "$conn_name" >/dev/null 2>&1 || warn "Failed to bring down connection '$conn_name' (it might be already down or managed externally)."
            log "Attempting to delete connection: $conn_name"
            nmcli connection delete "$conn_name" >/dev/null 2>&1 || warn "Failed to delete connection '$conn_name' (it might have been already deleted or managed externally)."
        fi
    done
    
    # Firewall cleanup is handled by the application service on stop.
    # No direct call to firewall-rules.sh here.
    
    success "Hotspot connection cleanup attempted."
}

# Remove installed files
remove_files() {
    log "Removing HotterSpot application files and configurations..."

    # Remove main installation directory (contains app, libs, venv)
    if [ -d "$INSTALL_DIR" ]; then
        log "Removing installation directory: $INSTALL_DIR"
        rm -rf "$INSTALL_DIR"
        success "Installation directory removed."
    else
        warn "Installation directory $INSTALL_DIR not found."
    fi
    
    # Remove desktop file
    if [ -f "$DESKTOP_FILE" ]; then
        log "Removing desktop file: $DESKTOP_FILE"
        rm -f "$DESKTOP_FILE"
        # Update desktop database
        if command -v update-desktop-database &> /dev/null; then
            update-desktop-database -q /usr/share/applications || warn "Failed to update desktop database."
        fi
        success "Desktop file removed."
    else
        warn "Desktop file $DESKTOP_FILE not found."
    fi
    
    # Remove binary symlink
    if [ -L "$BIN_LINK" ]; then
        log "Removing binary symlink: $BIN_LINK"
        rm -f "$BIN_LINK"
        success "Binary symlink removed."
    else
        warn "Binary symlink $BIN_LINK not found."
    fi
    
    # Remove systemd service file
    if [ -f "$SERVICE_FILE" ]; then
        log "Removing systemd service file: $SERVICE_FILE"
        rm -f "$SERVICE_FILE"
        log "Reloading systemd daemon..."
        systemctl daemon-reload || warn "Failed to reload systemd daemon."
        success "Systemd service file removed."
    else
        warn "Systemd service file $SERVICE_FILE not found."
    fi
    
    # Remove entire configuration directory
    if [ -d "$CONFIG_DIR_BASE" ]; then # Use CONFIG_DIR_BASE to remove the whole /etc/hotspot-manager
        log "Removing configuration directory: $CONFIG_DIR_BASE"
        rm -rf "$CONFIG_DIR_BASE"
        success "Configuration directory removed."
    else
        warn "Configuration directory $CONFIG_DIR_BASE not found."
    fi
    
    # Remove application log directory
    if [ -d "$LOG_DIR_APP" ]; then # LOG_DIR_APP is /var/log/hotspot-manager
        log "Removing log directory: $LOG_DIR_APP"
        rm -rf "$LOG_DIR_APP"
        success "Log directory removed."
    else
        warn "Log directory $LOG_DIR_APP not found."
    fi
    
    # Remove logrotate configuration
    if [ -f "$LOGROTATE_FILE" ]; then
        log "Removing logrotate configuration: $LOGROTATE_FILE"
        rm -f "$LOGROTATE_FILE"
        success "Logrotate configuration removed."
    else
        warn "Logrotate configuration $LOGROTATE_FILE not found."
    fi
    
    # Remove NetworkManager configuration file
    if [ -f "$NETWORKMANAGER_CONF" ]; then
        log "Removing NetworkManager configuration: $NETWORKMANAGER_CONF"
        rm -f "$NETWORKMANAGER_CONF"
        if command -v systemctl &> /dev/null && systemctl is-active --quiet NetworkManager &>/dev/null; then
            log "Restarting NetworkManager..."
            systemctl restart NetworkManager || warn "Failed to restart NetworkManager."
        fi
        success "NetworkManager configuration removed."
    else
        warn "NetworkManager configuration $NETWORKMANAGER_CONF not found."
    fi
    success "File and configuration removal process completed."
}

# Python packages are installed in a virtual environment within $INSTALL_DIR.
# Removing $INSTALL_DIR will remove the venv and its packages.
# So, remove_python_packages function is no longer needed.

# Main uninstall function
main() {
    log "Starting HotterSpot Uninstallation..."

    check_root
    
    # Add a confirmation prompt
    read -r -p "Are you sure you want to completely uninstall HotterSpot and remove all its configurations? [y/N] " response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        log "Proceeding with uninstallation."
    else
        log "Uninstallation cancelled by user."
        exit 0
    fi

    stop_service         # Stops and disables the systemd service
    cleanup_hotspots     # Cleans up NetworkManager connections
    remove_files         # Removes all files, directories, and configurations

    success "HotterSpot uninstallation completed."
    echo
    echo -e "${GREEN}HotterSpot has been uninstalled from your system.${NC}"
    echo "Some system services like NetworkManager might have been restarted."
    echo "If you had custom configurations in $CONFIG_DIR_BASE, they have been removed."
    echo "Log files in $LOG_DIR_APP have also been removed."
    echo "Please check for any residual files if you customized paths significantly."
}

# Run main function
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi