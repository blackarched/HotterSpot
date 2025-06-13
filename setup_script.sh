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
    log "Checking for python3-venv package..."
    case $DISTRO in
        "ubuntu"|"debian"|"linuxmint"|"pop"|"elementary")
            if ! dpkg -s python3-venv >/dev/null 2>&1; then
                log "python3-venv not found, installing..."
                apt install -y python3-venv
            fi
            ;;
        "fedora"|"centos"|"rhel"|"rocky"|"almalinux")
            if ! rpm -q python3-venv >/dev/null 2>&1; then # This check might vary
                log "python3-venv not found, installing..."
                if command -v dnf &> /dev/null; then
                    dnf install -y python3-venv # Or python3-virtualenv, package name can vary
                else
                    yum install -y python3-venv # Or python3-virtualenv
                fi
            fi
            ;;
        "arch"|"manjaro"|"endeavouros")
            if ! pacman -Q python-virtualenv >/dev/null 2>&1; then # Arch uses python-virtualenv
                log "python-virtualenv not found, installing..."
                pacman -S --noconfirm python-virtualenv
            fi
            ;;
        "opensuse"|"opensuse-leap"|"opensuse-tumbleweed")
             if ! rpm -q python3-virtualenv >/dev/null 2>&1; then # openSUSE might use python3-virtualenv
                log "python3-virtualenv not found, installing..."
                zypper install -y python3-virtualenv
            fi
            ;;
        *)
            warn "Could not automatically check/install venv package for $DISTRO. Please ensure python3 venv capabilities are available."
            ;;
    esac

    log "Creating Python virtual environment in $INSTALL_DIR/venv..."
    python3 -m venv "$INSTALL_DIR/venv"
    if [ ! -f "$INSTALL_DIR/venv/bin/python3" ]; then
        error "Failed to create Python virtual environment."
        error "Please ensure python3 and the appropriate venv package (e.g., python3-venv) are installed correctly."
        exit 1
    fi

    log "Installing Python dependencies from requirements.txt into virtual environment..."
    if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
        error "requirements.txt not found in $SCRIPT_DIR!"
        exit 1
    fi

    "$INSTALL_DIR/venv/bin/pip3" install -r "$SCRIPT_DIR/requirements.txt"
    if [ $? -ne 0 ]; then
        error "Failed to install Python dependencies from requirements.txt."
        # Optionally, you could add a fallback here to install packages individually if -r fails
        # For now, we'll keep it strict.
        exit 1
    fi
    success "Python dependencies installed into virtual environment."
}

# Create installation directory
setup_installation() {
    log "Setting up installation directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR/lib"
    # No separate bin directory for now, main script will be in $INSTALL_DIR
    # mkdir -p "$INSTALL_DIR/bin"

    # Copy all python files
    log "Copying Python application files..."
    if ls "$SCRIPT_DIR"/*.py > /dev/null 2>&1; then
        for py_file in "$SCRIPT_DIR"/*.py; do
            base_name=$(basename "$py_file")
            # Check if the file is not the setup script itself or the uninstall script
            if [ "$base_name" == "linux_hotspot_main.py" ]; then
                cp "$py_file" "$INSTALL_DIR/$base_name"
                chmod +x "$INSTALL_DIR/$base_name"
                log "Copied and made executable: $INSTALL_DIR/$base_name"
            elif [ "$base_name" != "setup_script.py" ] && [ "$base_name" != "$(basename "${BASH_SOURCE[0]}")" ] && [ "$base_name" != "uninstall_script.py" ]; then
                cp "$py_file" "$INSTALL_DIR/lib/"
                log "Copied to lib: $INSTALL_DIR/lib/$base_name"
            fi
        done
    else
        warn "No Python files (*.py) found in $SCRIPT_DIR to copy."
    fi
    
    # Copy uninstall script
    if [ -f "$SCRIPT_DIR/uninstall_script.sh" ]; then # Assuming it's uninstall_script.sh
        cp "$SCRIPT_DIR/uninstall_script.sh" "$INSTALL_DIR/"
        chmod +x "$INSTALL_DIR/uninstall_script.sh"
        log "Copied uninstall script."
    else
        warn "Uninstall script (uninstall_script.sh) not found in $SCRIPT_DIR."
    fi

    log "Creating symlink for main application..."
    # Symlink directly to the script in $INSTALL_DIR, which will be run via venv python
    ln -sf "$INSTALL_DIR/linux_hotspot_main.py" "$BIN_LINK"
    
    success "Application files installed and structured."
}

# Create desktop entry
create_desktop_entry() {
    log "Creating desktop entry..."
    
    # Ensure $INSTALL_DIR/venv/bin/python3 is the interpreter
    PYTHON_EXEC="$INSTALL_DIR/venv/bin/python3"
    MAIN_SCRIPT_EXEC="$INSTALL_DIR/linux_hotspot_main.py" # Main script is now in $INSTALL_DIR

    # Check if pkexec is available
    if ! command -v pkexec &> /dev/null; then
        warn "pkexec not found. Desktop entry will run the script directly, which might require manual password input or run without root privileges if not handled by the script."
        EXEC_CMD="$PYTHON_EXEC $MAIN_SCRIPT_EXEC"
    else
        EXEC_CMD="pkexec $PYTHON_EXEC $MAIN_SCRIPT_EXEC"
    fi

    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=HotterSpot
Comment=Linux WiFi Hotspot Management Tool
Exec=$EXEC_CMD
Icon=network-wireless-hotspot # A more specific generic icon, or use 'network-wireless'
Terminal=false
Type=Application
Categories=Network;System;
Keywords=hotspot;wifi;network;sharing;internet;
StartupNotify=true
X-Desktop-File-Install-Version=0.26 # Optional: for versioning the .desktop file itself
EOF
    
    # Validate desktop file
    if command -v desktop-file-validate &> /dev/null; then
        desktop-file-validate "$DESKTOP_FILE" || warn "Desktop file validation failed. There might be an issue with the generated .desktop file."
    else
        warn "desktop-file-validate command not found. Skipping desktop file validation."
    fi

    success "Desktop entry created at $DESKTOP_FILE"
}

# Setup systemd service (optional)
setup_systemd_service() {
    log "Setting up systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/hotspot-manager.service"
    # Use the python from the virtual environment
    PYTHON_EXEC="$INSTALL_DIR/venv/bin/python3"
    MAIN_SCRIPT="$INSTALL_DIR/linux_hotspot_main.py"

    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=HotterSpot Service
After=network.target

[Service]
Type=simple
# Ensure linux_hotspot_main.py handles daemonization correctly or change Type to forking
ExecStart=$PYTHON_EXEC $MAIN_SCRIPT --daemon
WorkingDirectory=$INSTALL_DIR
User=root # Consider if a non-root user could be used with appropriate capabilities
Group=root # Or a dedicated group
Restart=on-failure
RestartSec=5
StartLimitIntervalSec=0 # Or a reasonable interval like 60s with StartLimitBurst=5

# StandardOutput=journal # Or append to a log file
# StandardError=journal  # Or append to a log file

# Security hardening (optional, but recommended)
# PrivateTmp=true
# ProtectSystem=full
# NoNewPrivileges=true
# PrivateDevices=true
# ProtectHome=true
# ProtectKernelTunables=true
# ProtectKernelModules=true
# ProtectControlGroups=true
# RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
# SystemCallFilter=@system-service
# SystemCallArchitectures=native
# ReadWritePaths=/var/log/hotspot-manager /etc/hotspot-manager # Add paths the app needs to write to

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    log "Systemd service file created at $SERVICE_FILE"
    log "To enable and start: sudo systemctl enable --now hotspot-manager.service"
    success "Systemd service setup complete."
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

# (No setup_firewall function body anymore, it has been removed)

# Create configuration directory and copy default JSON configs
setup_config() {
    log "Setting up configuration directory..."
    
    CONFIG_DIR_MAIN="/etc/hotspot-manager"
    CONFIG_DIR_JSON="$CONFIG_DIR_MAIN/hotspot_config"

    mkdir -p "$CONFIG_DIR_JSON"
    if [ $? -ne 0 ]; then
        error "Failed to create configuration directory: $CONFIG_DIR_JSON"
        exit 1
    fi
    chmod 755 "$CONFIG_DIR_MAIN"
    chmod 755 "$CONFIG_DIR_JSON" # Or more restrictive if needed, e.g., 750 if group-managed

    # Remove old config.conf if it exists
    if [ -f "$CONFIG_DIR_MAIN/config.conf" ]; then
        log "Removing old config.conf file..."
        rm -f "$CONFIG_DIR_MAIN/config.conf"
    fi

    # Placeholder for copying default JSON configuration files
    # For example, if you have 'default_hotspot_settings.json' in SCRIPT_DIR:
    # if [ -f "$SCRIPT_DIR/default_hotspot_settings.json" ]; then
    #    log "Copying default_hotspot_settings.json to $CONFIG_DIR_JSON/"
    #    cp "$SCRIPT_DIR/default_hotspot_settings.json" "$CONFIG_DIR_JSON/"
    #    chmod 644 "$CONFIG_DIR_JSON/default_hotspot_settings.json"
    # else
    #    warn "No default_hotspot_settings.json found in $SCRIPT_DIR. Application will create one on first run."
    # fi
    # Repeat for other default JSON configs if any.

    success "Configuration directory setup at $CONFIG_DIR_JSON"
}

# Create log rotation
setup_logging() {
    log "Setting up logging..."
    
    LOG_DIR_APP="/var/log/hotspot-manager"
    LOG_FILE_APP="$LOG_DIR_APP/hotspot-manager.log" # Changed from /var/log/hotspot-manager.log

    mkdir -p "$LOG_DIR_APP"
    if [ $? -ne 0 ]; then
        error "Failed to create log directory: $LOG_DIR_APP"
        # Continue, as logging to /tmp might still work or user can fix permissions
    else
        # Set permissions for the log directory.
        # If service runs as root, 755 is fine. If as a specific user, adjust.
        chmod 755 "$LOG_DIR_APP"
        log "Log directory $LOG_DIR_APP created."
    fi

    # Update logrotate config to use the new path
    cat > /etc/logrotate.d/hotspot-manager << EOF
$LOG_FILE_APP {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    # If the service needs to be reloaded/restarted, use postrotate.
    # Example:
    # postrotate
    #    systemctl reload hotspot-manager.service > /dev/null 2>/dev/null || true
    # endscript
}
EOF
    
    # Touch the log file to ensure it exists with potentially correct ownership if script is run as non-root initially.
    # However, the service itself should create it with its running user's permissions.
    touch "$LOG_FILE_APP"
    # Permissions will be managed by the application/service, or logrotate.
    # chmod 640 "$LOG_FILE_APP"
    # chown root:adm "$LOG_FILE_APP" # Or appropriate user/group

    success "Logging configured. Main log file: $LOG_FILE_APP"
}

# Verify installation
verify_installation() {
    log "Verifying installation..."
    
    local all_ok=true

    # Check for main application script
    if [[ ! -f "$INSTALL_DIR/linux_hotspot_main.py" ]]; then
        error "Main application file ($INSTALL_DIR/linux_hotspot_main.py) not found."
        all_ok=false
    fi

    # Check for lib directory
    if [[ ! -d "$INSTALL_DIR/lib" ]]; then
        error "Library directory ($INSTALL_DIR/lib) not found."
        all_ok=false
    fi
    
    # Check for venv directory and python executable
    if [[ ! -f "$INSTALL_DIR/venv/bin/python3" ]]; then
        error "Python virtual environment interpreter ($INSTALL_DIR/venv/bin/python3) not found."
        all_ok=false
    fi

    if [[ ! -f "$DESKTOP_FILE" ]]; then
        error "Desktop file ($DESKTOP_FILE) not found."
        all_ok=false
    fi
    
    if [[ ! -L "$BIN_LINK" ]] || [[ "$(readlink -f "$BIN_LINK")" != "$INSTALL_DIR/linux_hotspot_main.py" ]]; then
        error "Binary symlink ($BIN_LINK) not found or not pointing to $INSTALL_DIR/linux_hotspot_main.py."
        all_ok=false
    fi

    # Test Python imports within the virtual environment
    log "Verifying Python dependencies within virtual environment..."
    if [ -f "$INSTALL_DIR/venv/bin/python3" ]; then
        "$INSTALL_DIR/venv/bin/python3" -c "
import sys
try:
    import PyQt5.QtWidgets
    import psutil
    import netifaces
    import Flask # Added Flask as per requirements.txt
    print('Python dependencies seem OK within the virtual environment.')
except ImportError as e:
    print(f'ERROR: Python dependency import error within virtual environment: {e}', file=sys.stderr)
    sys.exit(1)
"
        if [ $? -ne 0 ]; then
            error "Python dependency verification failed within the virtual environment."
            all_ok=false
        fi
    else
        error "Cannot verify Python dependencies: virtual environment python not found."
        all_ok=false
    fi
    
    # Check system tools
    local tools=("nmcli" "hostapd" "dnsmasq" "iptables" "iw")
    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            warn "System tool not found: $tool (This might be an issue for runtime)"
        fi
    done
    
    if [ "$all_ok" = true ]; then
        success "Installation verified successfully."
    else
        error "Installation verification failed. Please check the errors above."
        # The script will exit due to "set -e" if any command in verify_installation fails and returns non-zero.
        # If granular control is needed, remove "set -e" and handle exits explicitly.
        # For now, relying on "set -e" or explicit "exit 1" in called functions.
        return 1 # Indicate failure
    fi
}

# Main installation function
main() {
    # Ensure SCRIPT_DIR is set if not already
    # LOG_FILE is defined globally now. Let's update its name.
    # Clear previous log file
    LOG_FILE="/tmp/hotterspot-setup.log" # Changed log file name
    > "$LOG_FILE"

    log "Starting HotterSpot installation..." # Changed name
    
    check_root
    detect_distro

    # Create $INSTALL_DIR early so venv can be created there
    log "Creating base installation directory: $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    if [ $? -ne 0 ]; then
        error "Failed to create installation directory: $INSTALL_DIR"
        exit 1
    fi

    install_dependencies # Installs system packages
    install_python_deps  # Creates venv and installs Python packages from requirements.txt
    setup_installation   # Copies application files, sets up lib structure
    create_desktop_entry # Creates .desktop file for GUI launch
    setup_systemd_service # Sets up systemd service

    if command -v systemctl &> /dev/null && systemctl list-units --full -all | grep -q 'NetworkManager.service'; then
        # Check if NetworkManager is active before trying to configure it
        if systemctl is-active --quiet NetworkManager; then
            configure_networkmanager
        else
            warn "NetworkManager.service is present but not active. Skipping NetworkManager configuration."
        fi
    else
        warn "NetworkManager.service not detected. Skipping NetworkManager configuration."
        warn "Manual configuration might be needed if using NetworkManager and it's installed later."
    fi

    setup_config         # Creates configuration directories
    setup_logging        # Sets up logging directory and logrotate

    if ! verify_installation; then
         error "Installation failed due to verification errors. Please check the log: $LOG_FILE"
         exit 1
    fi
    
    success "HotterSpot installation completed successfully!"
    echo
    echo -e "${GREEN}HotterSpot has been installed successfully!${NC}"
    echo
    echo "Usage options:"
    echo "1. GUI: Search for 'HotterSpot' in your applications menu (may require a logout/login or system restart to appear)"
    echo "2. Command line symlink: hotspot-manager (Note: this symlink points to the script, not the venv python directly)"
    echo "   To run from command line with venv: sudo $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/linux_hotspot_main.py"
    echo "3. Systemd service: sudo systemctl start hotspot-manager.service (after enabling with: sudo systemctl enable hotspot-manager.service)"
    echo
    echo "Configuration files are located in: $CONFIG_DIR_JSON (Note: variable used from setup_config)"
    echo "Main application log file is: $LOG_FILE_APP (Note: variable used from setup_logging)"
    echo "Setup script log is: $LOG_FILE"
    echo
    echo -e "${YELLOW}Note: The application typically requires root privileges to manage network interfaces and services.${NC}"
    echo -e "${YELLOW}The .desktop entry uses 'pkexec' to request these privileges. The systemd service runs as root.${NC}"
    echo
}

# Run main function if the script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi