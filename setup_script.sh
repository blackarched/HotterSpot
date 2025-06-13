#!/bin/bash

# Linux Hotspot Manager - Setup Script
# This script installs dependencies and sets up the hotspot manager

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/hotspot-manager"
DESKTOP_FILE="/usr/share/applications/hotspot-manager.desktop"
BIN_LINK="/usr/local/bin/hotspot-manager"

# Logging
LOG_FILE="/tmp/hotspot-manager-setup.log"

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "[$(date)] INFO: $1" >> "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    echo "[$(date)] WARN: $1" >> "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[$(date)] ERROR: $1" >> "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    echo "[$(date)] SUCCESS: $1" >> "$LOG_FILE"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Detect Linux distribution
detect_distro() {
    log "Detecting Linux distribution..."
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
    elif [ -f /etc/redhat-release ]; then
        DISTRO="rhel"
    elif [ -f /etc/debian_version ]; then
        DISTRO="debian"
    else
        DISTRO="unknown"
    fi
    
    log "Detected distribution: $DISTRO"
}

# Install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    
    case $DISTRO in
        "ubuntu"|"debian"|"linuxmint"|"pop"|"elementary")
            apt update
            apt install -y \
                python3 \
                python3-pip \
                python3-venv \
                hostapd \
                dnsmasq \
                iptables \
                iw \
                wireless-tools \
                net-tools \
                network-manager \
                python3-pyqt5 \
                python3-pyqt5.qtwidgets \
                python3-netifaces \
                python3-psutil
            ;;
        "fedora"|"centos"|"rhel"|"rocky"|"almalinux")
            if command -v dnf &> /dev/null; then
                DNF_CMD="dnf"
            else
                DNF_CMD="yum"
            fi
            
            $DNF_CMD update -y
            $DNF_CMD install -y \
                python3 \
                python3-pip \
                hostapd \
                dnsmasq \
                iptables \
                iw \
                wireless-tools \
                net-tools \
                NetworkManager \
                python3-qt5 \
                python3-netifaces \
                python3-psutil
            ;;
        "arch"|"manjaro"|"endeavouros")
            pacman -Syu --noconfirm
            pacman -S --noconfirm \
                python \
                python-pip \
                hostapd \
                dnsmasq \
                iptables \
                iw \
                wireless_tools \
                net-tools \
                networkmanager \
                python-pyqt5 \
                python-netifaces \
                python-psutil
            ;;
        "opensuse"|"opensuse-leap"|"opensuse-tumbleweed")
            zypper refresh
            zypper install -y \
                python3 \
                python3-pip \
                hostapd \
                dnsmasq \
                iptables \
                iw \
                wireless-tools \
                net-tools \
                NetworkManager \
                python3-qt5 \
                python3-netifaces \
                python3-psutil
            ;;
        *)
            error "Unsupported distribution: $DISTRO"
            warn "Please install dependencies manually:"
            warn "- Python 3 with PyQt5"
            warn "- hostapd, dnsmasq, iptables"
            warn "- NetworkManager, iw, wireless-tools"
            ;;
    esac
    
    success "System dependencies installed"
}

# Install Python dependencies
install_python_deps() {
    log "Installing Python dependencies..."
    
    # Try to install using pip if system packages are not available
    pip3 install --break-system-packages 2>/dev/null || pip3 install \
        PyQt5 \
        psutil \
        netifaces \
        configparser
    
    success "Python dependencies installed"
}

# Create installation directory
setup_installation() {
    log "Setting up installation directory..."
    
    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    
    # Copy files
    cp "$SCRIPT_DIR/hotspot_manager.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/uninstall.sh" "$INSTALL_DIR/" 2>/dev/null || true
    
    # Make executable
    chmod +x "$INSTALL_DIR/hotspot_manager.py"
    
    # Create symlink
    ln -sf "$INSTALL_DIR/hotspot_manager.py" "$BIN_LINK"
    
    success "Installation directory created"
}

# Create desktop entry
create_desktop_entry() {
    log "Creating desktop entry..."
    
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Hotspot Manager
Comment=Linux WiFi Hotspot Manager
Exec=pkexec $INSTALL_DIR/hotspot_manager.py
Icon=network-wireless
Terminal=false
Type=Application
Categories=Network;System;
Keywords=hotspot;wifi;network;sharing;
StartupNotify=true
EOF
    
    success "Desktop entry created"
}

# Setup systemd service (optional)
setup_systemd_service() {
    log "Setting up systemd service..."
    
    cat > /etc/systemd/system/hotspot-manager.service << EOF
[Unit]
Description=Hotspot Manager Service
After=network.target

[Service]
Type=simple
ExecStart=$INSTALL_DIR/hotspot_manager.py --daemon
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    
    success "Systemd service created (not enabled by default)"
}

# Configure NetworkManager
configure_networkmanager() {
    log "Configuring NetworkManager..."
    
    # Create NetworkManager configuration
    cat > /etc/NetworkManager/conf.d/hotspot-manager.conf << EOF
[main]
# Configuration for Hotspot Manager
no-auto-default=*

[connection]
# Allow hotspot connections
wifi.powersave=2

[device]
# Manage all WiFi devices
wifi.scan-rand-mac-address=no
EOF
    
    # Restart NetworkManager
    systemctl restart NetworkManager
    
    success "NetworkManager configured"
}

# Setup firewall rules
setup_firewall() {
    log "Setting up firewall rules..."
    
    # Create iptables rules script
    cat > "$INSTALL_DIR/firewall-rules.sh" << 'EOF'
#!/bin/bash

# Hotspot Manager Firewall Rules

HOTSPOT_INTERFACE="wlan0"  # Default, will be updated by application
INTERNET_INTERFACE="eth0"   # Default, will be updated by application

setup_rules() {
    # Enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward
    
    # NAT rules
    iptables -t nat -A POSTROUTING -o $INTERNET_INTERFACE -j MASQUERADE
    iptables -A FORWARD -i $INTERNET_INTERFACE -o $HOTSPOT_INTERFACE -m state --state RELATED,ESTABLISHED -j ACCEPT
    iptables -A FORWARD -i $HOTSPOT_INTERFACE -o $INTERNET_INTERFACE -j ACCEPT
    
    # DNS redirection (for captive portal)
    iptables -t nat -A PREROUTING -i $HOTSPOT_INTERFACE -p udp --dport 53 -j REDIRECT --to-port 53
    iptables -t nat -A PREROUTING -i $HOTSPOT_INTERFACE -p tcp --dport 53 -j REDIRECT --to-port 53
}

cleanup_rules() {
    # Remove NAT rules
    iptables -t nat -D POSTROUTING -o $INTERNET_INTERFACE -j MASQUERADE 2>/dev/null || true
    iptables -D FORWARD -i $INTERNET_INTERFACE -o $HOTSPOT_INTERFACE -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
    iptables -D FORWARD -i $HOTSPOT_INTERFACE -o $INTERNET_INTERFACE -j ACCEPT 2>/dev/null || true
    
    # Remove DNS redirection
    iptables -t nat -D PREROUTING -i $HOTSPOT_INTERFACE -p udp --dport 53 -j REDIRECT --to-port 53 2>/dev/null || true
    iptables -t nat -D PREROUTING -i $HOTSPOT_INTERFACE -p tcp --dport 53 -j REDIRECT --to-port 53 2>/dev/null || true
}

case "$1" in
    setup)
        setup_rules
        ;;
    cleanup)
        cleanup_rules
        ;;
    *)
        echo "Usage: $0 {setup|cleanup}"
        exit 1
        ;;
esac
EOF
    
    chmod +x "$INSTALL_DIR/firewall-rules.sh"
    
    success "Firewall rules script created"
}

# Create configuration directory
setup_config() {
    log "Setting up configuration..."
    
    mkdir -p /etc/hotspot-manager
    
    cat > /etc/hotspot-manager/config.conf << EOF
[general]
default_ssid=HotspotManager
default_interface=wlan0
log_level=INFO
log_file=/var/log/hotspot-manager.log

[security]
min_password_length=8
default_encryption=WPA2
allow_wps=false

[network]
default_channel=6
default_ip_range=192.168.4.0/24
default_gateway=192.168.4.1
dhcp_range_start=192.168.4.10
dhcp_range_end=192.168.4.50

[advanced]
max_clients=50
beacon_interval=100
dtim_period=2
rts_threshold=2347
fragm_threshold=2346
EOF
    
    success "Configuration files created"
}

# Create log rotation
setup_logging() {
    log "Setting up logging..."
    
    cat > /etc/logrotate.d/hotspot-manager << EOF
/var/log/hotspot-manager.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    postrotate
        systemctl reload hotspot-manager 2>/dev/null || true
    endscript
}
EOF
    
    touch /var/log/hotspot-manager.log
    chmod 644 /var/log/hotspot-manager.log
    
    success "Logging configured"
}

# Verify installation
verify_installation() {
    log "Verifying installation..."
    
    # Check if files exist
    if [[ ! -f "$INSTALL_DIR/hotspot_manager.py" ]]; then
        error "Main application file not found"
        return 1
    fi
    
    if [[ ! -f "$DESKTOP_FILE" ]]; then
        error "Desktop file not found"
        return 1
    fi
    
    if [[ ! -L "$BIN_LINK" ]]; then
        error "Binary symlink not found"
        return 1
    fi
    
    # Test Python imports
    python3 -c "
import sys
try:
    from PyQt5.QtWidgets import QApplication
    import psutil
    import netifaces
    print('Python dependencies OK')
except ImportError as e:
    print(f'Python dependency error: {e}')
    sys.exit(1)
" || return 1
    
    # Check system tools
    local tools=("nmcli" "hostapd" "dnsmasq" "iptables" "iw")
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            warn "Tool not found: $tool"
        fi
    done
    
    success "Installation verified"
}

# Main installation function
main() {
    log "Starting Hotspot Manager installation..."
    
    check_root
    detect_distro
    install_dependencies
    install_python_deps
    setup_installation
    create_desktop_entry
    setup_systemd_service
    configure_networkmanager
    setup_firewall
    setup_config
    setup_logging
    verify_installation
    
    success "Installation completed successfully!"
    echo
    echo -e "${GREEN}Hotspot Manager has been installed successfully!${NC}"
    echo
    echo "Usage options:"
    echo "1. GUI: Search for 'Hotspot Manager' in your applications menu"
    echo "2. Command line: hotspot-manager"
    echo "3. Direct: sudo $INSTALL_DIR/hotspot_manager.py"
    echo
    echo "Configuration files are located in /etc/hotspot-manager/"
    echo "Logs are written to /var/log/hotspot-manager.log"
    echo
    echo -e "${YELLOW}Note: The application requires root privileges to manage network interfaces.${NC}"
    echo
}

# Run main function
main "$@"