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

# Installation paths
INSTALL_DIR="/opt/hotspot-manager"
DESKTOP_FILE="/usr/share/applications/hotspot-manager.desktop"
BIN_LINK="/usr/local/bin/hotspot-manager"
SERVICE_FILE="/etc/systemd/system/hotspot-manager.service"
CONFIG_DIR="/etc/hotspot-manager"
LOG_FILE="/var/log/hotspot-manager.log"
LOGROTATE_FILE="/etc/logrotate.d/hotspot-manager"
NETWORKMANAGER_CONF="/etc/NetworkManager/conf.d/hotspot-manager.conf"

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
    log "Stopping hotspot manager service..."
    
    if systemctl is-active --quiet hotspot-manager 2>/dev/null; then
        systemctl stop hotspot-manager
        log "Service stopped"
    fi
    
    if systemctl is-enabled --quiet hotspot-manager 2>/dev/null; then
        systemctl disable hotspot-manager
        log "Service disabled"
    fi
}

# Clean up any running hotspots
cleanup_hotspots() {
    log "Cleaning up any running hotspots..."
    
    # Stop any NetworkManager hotspot connections
    nmcli connection show --active | grep -i hotspot | while read line; do
        conn_name=$(echo "$line" | awk '{print $1}')
        nmcli connection down "$conn_name" 2>/dev/null || true
        nmcli connection delete "$conn_name" 2>/dev/null || true
    done
    
    # Clean up iptables rules
    if [[ -f "$INSTALL_DIR/firewall-rules.sh" ]]; then
        "$INSTALL_DIR/firewall-rules.sh" cleanup 2>/dev/null || true
    fi
    
    success "Hotspots cleaned up"
}

# Remove installed files
remove_files() {
    log "Removing installed files..."
    
    # Remove main installation directory
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        success "Installation directory removed"
    fi
    
    # Remove desktop file
    if [[ -f "$DESKTOP_FILE" ]]; then
        rm -f "$DESKTOP_FILE"
        success "Desktop file removed"
    fi
    
    # Remove binary symlink
    if [[ -L "$BIN_LINK" ]]; then
        rm -f "$BIN_LINK"
        success "Binary symlink removed"
    fi
    
    # Remove systemd service
    if [[ -f "$SERVICE_FILE" ]]; then
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        success "Systemd service removed"
    fi
    
    # Remove configuration directory
    if [[ -d "$CONFIG_DIR" ]]; then
        rm -rf "$CONFIG_DIR"
        success "Configuration directory removed"
    fi
    
    # Remove log file
    if [[ -f "$LOG_FILE" ]]; then
        rm -f "$LOG_FILE"
        success "Log file removed"
    fi
    
    # Remove logrotate configuration
    if [[ -f "$LOGROTATE_FILE" ]]; then
        rm -f "$LOGROTATE_FILE"
        success "Logrotate configuration removed"
    fi
    
    # Remove NetworkManager configuration
    if [[ -f "$NETWORKMANAGER_CONF" ]]; then
        rm -f "$NETWORKMANAGER_CONF"
        systemctl restart NetworkManager 2>/dev/null || true
        success "NetworkManager configuration removed"
    fi
}

# Remove Python packages (optional)
remove_python_packages() {
    read -p "Do you want to remove Python packages that were installed? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Removing Python packages..."
        
        pip3 uninstall -y PyQt