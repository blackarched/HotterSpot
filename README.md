# HotterSpot

## Brief Description
HotterSpot is a comprehensive Linux Hotspot Management Tool designed to provide an easy-to-use and powerful interface for creating, managing, and monitoring a wireless hotspot on a Linux system.

## Key Features
- **Easy Hotspot Creation & Management:** Quickly set up a hotspot with custom SSID, password, and network interface selection.
- **Connected Device Monitoring and Management:** View a list of connected devices, block unwanted devices, and assign custom names for easier identification.
- **Bandwidth Control:** Set overall bandwidth limits for connected users to manage network usage effectively.
- **Captive Portal:** Implement a captive portal for user authentication or terms of service acceptance before granting network access.
- **Customizable DNS & DHCP:** Advanced configuration options for DNS and DHCP settings using dnsmasq.
- **Security Features:** Supports WPA2/WPA3 encryption and MAC address filtering for enhanced security.
- **System Monitoring:** Monitor system resources such as CPU usage, memory consumption, and network traffic.
- **Service Management:** Integrates with systemd for robust management of underlying hotspot services.
- **Backup and Restore:** Easily back up and restore hotspot configurations.
- **GUI Dashboard:** A user-friendly graphical interface built with PyQt5 for intuitive operation.
- **Production-ready Logging:** Comprehensive logging for diagnostics and monitoring.

## System Requirements and Permissions

HotterSpot is a powerful network management tool for Linux and therefore requires **root privileges** to perform many of its core operations.

**Why Root is Needed:**

*   Managing network interfaces and connections (via NetworkManager/nmcli).
*   Configuring the `iptables` firewall for NAT, device blocking, and captive portal.
*   Starting and stopping system services like `hostapd` (for WiFi AP) and `dnsmasq` (for DHCP/DNS).
*   Modifying system network configurations (e.g., IP forwarding).
*   Writing configuration files to system directories (e.g., `/etc/hotspot-manager/`, `/etc/NetworkManager/conf.d/`).
*   Creating and managing system log files in `/var/log/hotspot-manager/`.

**How HotterSpot Obtains Privileges:**

*   **GUI Application:** When launched from your desktop environment (via the `hotterspot.desktop` file), HotterSpot will use `pkexec` (PolicyKit Execute) to prompt you for your administrative password. This ensures that only authorized users can run the application with elevated permissions.
*   **Systemd Service:** If you enable and run HotterSpot as a system service (e.g., for headless operation or auto-start), the `hotterspot.service` unit is configured by default to run as the `root` user. This is specified in the service file located at `/etc/systemd/system/hotterspot.service`.
*   **Direct CLI Execution (Setup/Development):**
    *   The `setup_script.sh` must be run with `sudo` to install dependencies and set up system configurations.
    *   If you are running the main application script (`linux_hotspot_main.py`) directly from the terminal (e.g., for development purposes), you must also use `sudo` or `pkexec` for it to function correctly:
        ```bash
        sudo /opt/hotspot-manager/venv/bin/python3 /opt/hotspot-manager/linux_hotspot_main.py
        ```
        or
        ```bash
        pkexec /opt/hotspot-manager/venv/bin/python3 /opt/hotspot-manager/linux_hotspot_main.py
        ```

**System Dependencies:**

HotterSpot relies on several standard Linux utilities and Python. The `setup_script.sh` will attempt to install these based on your distribution. Key dependencies include:
*   `NetworkManager` (and `nmcli`)
*   `hostapd`
*   `dnsmasq`
*   `iptables`
*   `iw` (and `wireless-tools`)
*   `python3`, `python3-pip`, `python3-venv`
*   Python libraries as listed in `requirements.txt` (e.g., `PyQt5`, `psutil`, `Flask`, `netifaces`).

(See the Installation section below for more details on distribution-specific packages and setup.)

## Installation Instructions
*(Placeholder for detailed installation steps)*

This section will include:
- List of dependencies (e.g., `dnsmasq`, `hostapd`, Python libraries)
- Instructions on how to run the `setup_script.sh`
- Manual installation steps (if applicable)

## Usage
*(Placeholder for usage instructions)*

This section will cover:
- How to launch the HotterSpot application.
- An overview of the GUI dashboard and its components.
- Basic operations like starting/stopping the hotspot, changing settings, etc.

## Configuration Details
*(Placeholder for advanced configuration)*

This section will detail:
- Paths to configuration files.
- Explanation of key configuration parameters.
- How to customize advanced settings (e.g., dnsmasq rules, captive portal pages).

## Troubleshooting
*(Placeholder for troubleshooting common issues)*

This section will provide:
- Solutions to common problems.
- How to interpret log files for debugging.
- Steps for reporting issues.

## Contributing
*(Placeholder for contribution guidelines)*

We welcome contributions to HotterSpot! Please refer to this section for:
- How to report bugs or suggest features.
- Guidelines for submitting pull requests.
- Coding standards (if any).

## License
This project is licensed under the terms of the license specified in the `LICENSE` file.