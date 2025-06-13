#!/usr/bin/env python3
"""
Service management and installation system for hotspot manager
Handles auto-start, watchdog processes, and system integration
"""

import os
import subprocess
import time
import threading
import signal
import psutil
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import json
from production_logger import get_logger
from error_handler import get_error_handler, with_error_handling, ErrorCategory, ErrorSeverity
from input_validator import get_validator, ValidationError

class ServiceStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass
class ServiceConfig:
    name: str
    description: str
    exec_path: str
    user: str = "root"
    group: str = "root"
    restart_policy: str = "always"
    dependencies: List[str] = None
    environment: Dict[str, str] = None
    working_directory: str = "/opt/hotspot-manager"

class ServiceManager:
    """System service management and integration"""
    
    def __init__(self):
        self.validator = get_validator()
        self.logger = get_logger()
        self.error_handler = get_error_handler()
        self.services = {}
        self.watchdog_active = False
        self.watchdog_thread = None
        self._lock = threading.Lock()
        
        # Paths
        self.install_dir = Path("/opt/hotspot-manager")
        self.config_dir = Path("/etc/hotspot-manager")
        self.log_dir = Path("/var/log/hotspot-manager")
        self.systemd_dir = Path("/etc/systemd/system")
        
        # Register shutdown handler
        self.error_handler.register_shutdown_handler(self.cleanup)
    
    @with_error_handling(ErrorCategory.SYSTEM, "install_service", ErrorSeverity.HIGH)
    def install_service(self, config: ServiceConfig) -> bool:
        """Install service with systemd integration"""
        
        self.logger.info(f"Installing service: {config.name}", component="service_manager")
        
        # Create directories
        self._create_directories()
        
        # Copy application files
        self._install_application_files()
        
        # Create systemd service file
        service_content = self._generate_systemd_service(config)
        service_file = self.systemd_dir / f"{config.name}.service"
        
        try:
            service_file.write_text(service_content)
            os.chmod(service_file, 0o644)
        except IOError as e:
            self.logger.error(f"Failed to create service file: {e}", component="service_manager")
            return False
        
        # Reload systemd and enable service
        try:
            # Assuming service name should conform to filename-like rules, or a specific service name pattern
            validated_service_name = self.validator.validate(config.name, 'filename', context="service_mgr_install_service_name")
        except ValidationError as e:
            self.logger.error(f"Invalid service name for installation: {config.name}. Error: {e}", component="service_manager")
            return False

        commands = [
            ["systemctl", "daemon-reload"],
            ["systemctl", "enable", validated_service_name],
        ]
        
        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                self.logger.error(
                    f"Command failed: {' '.join(cmd)}\nError: {result.stderr}",
                    component="service_manager"
                )
                # Clean up service file if enable failed?
                if service_file.exists():
                    service_file.unlink(missing_ok=True)
                return False
        
        self.services[validated_service_name] = config # Store with validated name if it's used as key elsewhere
        self.logger.audit("service_installed", details={"service": config.name})
        return True
    
    @with_error_handling(ErrorCategory.SYSTEM, "uninstall_service", ErrorSeverity.MEDIUM)
    def uninstall_service(self, service_name: str) -> bool:
        """Uninstall service and cleanup"""
        
        self.logger.info(f"Uninstalling service: {service_name}", component="service_manager")
        
        # Stop service first
        self.stop_service(service_name)
        
        try:
            validated_service_name = self.validator.validate(service_name, 'filename', context="service_mgr_uninstall_service_name")
        except ValidationError as e:
            self.logger.error(f"Invalid service name for uninstallation: {service_name}. Error: {e}", component="service_manager")
            return False

        # Disable and remove service
        commands = [
            ["systemctl", "disable", validated_service_name],
            ["systemctl", "daemon-reload"]
        ]
        
        for cmd in commands:
            subprocess.run(cmd, capture_output=True, text=True, check=False) # Allow failure if service not found
        
        # Remove service file
        service_file = self.systemd_dir / f"{validated_service_name}.service"
        if service_file.exists():
            try:
                service_file.unlink()
            except OSError as e_unlink:
                self.logger.warning(f"Could not remove service file {service_file}: {e_unlink}", component="service_manager")

        # Remove from tracking
        if validated_service_name in self.services:
            del self.services[validated_service_name]
        
        self.logger.audit("service_uninstalled", details={"service": service_name})
        return True
    
    @with_error_handling(ErrorCategory.SYSTEM, "start_service", ErrorSeverity.MEDIUM)
    def start_service(self, service_name: str) -> bool:
        """Start system service"""
        try:
            validated_service_name = self.validator.validate(service_name, 'filename', context="service_mgr_start_service_name")
        except ValidationError as e:
            self.logger.error(f"Invalid service name for start: {service_name}. Error: {e}", component="service_manager")
            return False
        
        result = subprocess.run(
            ["systemctl", "start", validated_service_name],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode == 0:
            self.logger.info(f"Service started: {validated_service_name}", component="service_manager")
            self.logger.audit("service_started", details={"service": service_name})
            return True
        else:
            self.logger.error(
                f"Failed to start service {service_name}: {result.stderr}",
                component="service_manager"
            )
            return False
    
    @with_error_handling(ErrorCategory.SYSTEM, "stop_service", ErrorSeverity.MEDIUM)
    def stop_service(self, service_name: str) -> bool:
        """Stop system service"""
        try:
            validated_service_name = self.validator.validate(service_name, 'filename', context="service_mgr_stop_service_name")
        except ValidationError as e:
            self.logger.error(f"Invalid service name for stop: {service_name}. Error: {e}", component="service_manager")
            return False

        result = subprocess.run(
            ["systemctl", "stop", validated_service_name],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode == 0:
            self.logger.info(f"Service stopped: {validated_service_name}", component="service_manager")
            self.logger.audit("service_stopped", details={"service": service_name})
            return True
        else:
            self.logger.error(
                f"Failed to stop service {service_name}: {result.stderr}",
                component="service_manager"
            )
            return False
    
    def get_service_status(self, service_name: str) -> ServiceStatus:
        """Get current service status"""
        try:
            validated_service_name = self.validator.validate(service_name, 'filename', context="service_mgr_status_service_name")
        except ValidationError as e:
            self.logger.error(f"Invalid service name for status check: {service_name}. Error: {e}", component="service_manager")
            return ServiceStatus.UNKNOWN

        try:
            result = subprocess.run(
                ["systemctl", "is-active", validated_service_name],
                capture_output=True, text=True, check=False
            )
            
            status_map = {
                "active": ServiceStatus.RUNNING,
                "inactive": ServiceStatus.STOPPED,
                "failed": ServiceStatus.FAILED,
                "activating": ServiceStatus.STARTING,
                "deactivating": ServiceStatus.STOPPING
            }
            
            return status_map.get(result.stdout.strip(), ServiceStatus.UNKNOWN)
            
        except Exception:
            return ServiceStatus.UNKNOWN
    
    def restart_service(self, service_name: str) -> bool:
        """Restart system service"""
        try:
            validated_service_name = self.validator.validate(service_name, 'filename', context="service_mgr_restart_service_name")
        except ValidationError as e:
            self.logger.error(f"Invalid service name for restart: {service_name}. Error: {e}", component="service_manager")
            return False

        result = subprocess.run(
            ["systemctl", "restart", validated_service_name],
            capture_output=True, text=True, check=False
        )
        
        if result.returncode == 0:
            self.logger.info(f"Service restarted: {validated_service_name}", component="service_manager")
            self.logger.audit("service_restarted", details={"service": service_name})
            return True
        else:
            self.logger.error(
                f"Failed to restart service {service_name}: {result.stderr}",
                component="service_manager"
            )
            return False
    
    def start_watchdog(self, check_interval: int = 30):
        """Start service watchdog monitoring"""
        
        if self.watchdog_active:
            return
        
        self.watchdog_active = True
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            args=(check_interval,),
            daemon=True
        )
        self.watchdog_thread.start()
        
        self.logger.info("Service watchdog started", component="service_manager")
    
    def stop_watchdog(self):
        """Stop service watchdog"""
        
        self.watchdog_active = False
        if self.watchdog_thread:
            self.watchdog_thread.join(timeout=5)
        
        self.logger.info("Service watchdog stopped", component="service_manager")
    
    def _watchdog_loop(self, check_interval: int):
        """Watchdog monitoring loop"""
        
        while self.watchdog_active:
            try:
                for service_name in self.services:
                    status = self.get_service_status(service_name)
                    
                    if status == ServiceStatus.FAILED:
                        self.logger.warning(
                            f"Service {service_name} failed, attempting restart",
                            component="watchdog"
                        )
                        
                        if self.restart_service(service_name):
                            self.logger.info(
                                f"Service {service_name} restarted successfully",
                                component="watchdog"
                            )
                        else:
                            self.logger.error(
                                f"Failed to restart service {service_name}",
                                component="watchdog"
                            )
                            
                            # Log security event for critical service failure
                            self.logger.security(
                                "critical_service_failure",
                                "high",
                                details={"service": service_name}
                            )
                
                time.sleep(check_interval)
                
            except Exception as e:
                self.logger.error(
                    f"Watchdog error: {e}",
                    component="watchdog",
                    exc_info=True
                )
                time.sleep(check_interval)
    
    def _create_directories(self):
        """Create necessary directories"""
        
        directories = [
            (self.install_dir, 0o755),
            (self.config_dir, 0o755),
            (self.log_dir, 0o755),
            (self.install_dir / "bin", 0o755),
            (self.install_dir / "lib", 0o755),
            (self.config_dir / "backup", 0o755)
        ]
        
        for directory, mode in directories:
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, mode)
    
    def _install_application_files(self):
        """Install application files to system directories"""
        
        # Get current script directory
        current_dir = Path(__file__).parent.absolute()
        
        # Files to install
        files_to_install = [
            ("main.py", "bin/hotspot-manager"),
            ("manager.py", "bin/manager.py"),
            ("config_manager.py", "lib/config_manager.py"),
            ("device_manager.py", "lib/device_manager.py"),
            ("network_monitor.py", "lib/network_monitor.py"),
            ("production_logger.py", "lib/production_logger.py"),
            ("error_handler.py", "lib/error_handler.py"),
            ("input_validator.py", "lib/input_validator.py"),
            # Add all other Python files...
        ]
        
        for src_file, dest_path in files_to_install:
            src_path = current_dir / src_file
            dest_full_path = self.install_dir / dest_path
            
            if src_path.exists():
                try:
                    # Create destination directory if needed
                    dest_full_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(src_path, dest_full_path)
                    
                    # Set permissions
                    if dest_path.startswith("bin/"):
                        os.chmod(dest_full_path, 0o755)  # Executable
                    else:
                        os.chmod(dest_full_path, 0o644)  # Readable
                        
                except IOError as e:
                    self.logger.error(
                        f"Failed to install {src_file}: {e}",
                        component="service_manager"
                    )
    
    def _generate_systemd_service(self, config: ServiceConfig) -> str:
        """Generate systemd service file content"""
        
        dependencies = config.dependencies or []
        after_deps = " ".join(dependencies)
        requires_deps = " ".join(dependencies)
        
        environment_vars = ""
        if config.environment:
            for key, value in config.environment.items():
                environment_vars += f"Environment={key}={value}\n"
        
        service_content = f"""[Unit]
Description={config.description}
After=network.target {after_deps}
Requires={requires_deps}
StartLimitIntervalSec=0

[Service]
Type=simple
User={config.user}
Group={config.group}
ExecStart={config.exec_path}
WorkingDirectory={config.working_directory}
        Restart={self.validator.validate(config.restart_policy, 'user_input', context="service_config_restart_policy")}
RestartSec=5
StandardOutput=journal
StandardError=journal
{environment_vars}
# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={self.log_dir} {self.config_dir}
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"""
        return service_content
    
    def get_service_logs(self, service_name: str, lines: int = 100) -> str:
        """Get service logs from journald"""
        try:
            validated_service_name = self.validator.validate(service_name, 'filename', context="service_mgr_logs_service_name")
            # Ensure 'lines' is a valid number
            if not isinstance(lines, int) or lines <= 0:
                lines = 100 # default to 100 if invalid
        except ValidationError as e:
            self.logger.error(f"Invalid service name for logs: {service_name}. Error: {e}", component="service_manager")
            return f"Invalid service name: {service_name}"

        try:
            result = subprocess.run(
                ["journalctl", "-u", validated_service_name, "-n", str(lines), "--no-pager"],
                capture_output=True, text=True, check=False
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return f"Error getting logs for {validated_service_name}: {result.stderr}"
                
        except Exception as e:
            return f"Error getting logs for {validated_service_name}: {e}"
    
    def cleanup(self):
        """Cleanup on shutdown"""
        
        self.logger.info("Service manager cleanup started", component="service_manager")
        
        # Stop watchdog
        self.stop_watchdog()
        
        # Perform any additional cleanup
        self.logger.info("Service manager cleanup completed", component="service_manager")


class ProcessManager:
    """Process management and monitoring"""
    
    def __init__(self):
        self.logger = get_logger()
        self.processes = {}
        self._lock = threading.Lock()
    
    def start_process(self, name: str, command: List[str], 
                     cwd: str = None, env: Dict[str, str] = None) -> Optional[int]:
        """Start a managed process"""
        
        try:
            # Validate each part of the command list if it can come from external source.
            # Here, we assume 'command' list itself is constructed safely, but its *elements*
            # should be validated if they originate from user input or config files.
            # For example, if command = ['/usr/bin/myprog', user_supplied_arg1, user_supplied_arg2],
            # then user_supplied_arg1 and user_supplied_arg2 need prior validation.
            # The 'command' rule in input_validator is for a single command string, not list elements.

            # Basic check: ensure all parts of command are strings
            if not all(isinstance(arg, str) for arg in command):
                self.logger.error(f"Command list for process '{name}' contains non-string arguments.", component="process_manager")
                return None

            # Further validation would depend on the source of 'command' elements.
            # If command[0] (the executable) can be influenced by external input, it's high risk.
            # For now, we proceed assuming 'command' is constructed with validated/safe components.

            proc = subprocess.Popen(
                command, # Use the validated command list
                cwd=cwd, # cwd should be validated if from external source
                env=env, # env vars should be validated if from external source
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True # Detaches from parent, good for services
            )
            
            with self._lock:
                self.processes[name] = {
                    'process': proc,
                    'command': command,
                    'start_time': time.time(),
                    'restart_count': 0
                }
            
            self.logger.info(
                f"Process started: {name} (PID: {proc.pid})",
                component="process_manager"
            )
            
            return proc.pid
            
        except Exception as e:
            self.logger.error(
                f"Failed to start process {name}: {e}",
                component="process_manager",
                exc_info=True
            )
            return None
    
    def stop_process(self, name: str, timeout: int = 10) -> bool:
        """Stop a managed process"""
        
        with self._lock:
            if name not in self.processes:
                return False
            
            proc_info = self.processes[name]
            proc = proc_info['process']
        
        try:
            # Try graceful shutdown first
            proc.terminate()
            
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                proc.kill()
                proc.wait()
            
            with self._lock:
                del self.processes[name]
            
            self.logger.info(f"Process stopped: {name}", component="process_manager")
            return True
            
        except Exception as e:
            self.logger.error(
                f"Failed to stop process {name}: {e}",
                component="process_manager",
                exc_info=True
            )
            return False
    
    def restart_process(self, name: str) -> bool:
        """Restart a managed process"""
        
        with self._lock:
            if name not in self.processes:
                return False
            
            proc_info = self.processes[name]
            command = proc_info['command']
        
        # Stop the process
        if not self.stop_process(name):
            return False
        
        # Start it again
        pid = self.start_process(name, command)
        
        if pid:
            with self._lock:
                self.processes[name]['restart_count'] += 1
            return True
        
        return False
    
    def get_process_status(self, name: str) -> Dict[str, Any]:
        """Get process status information"""
        
        with self._lock:
            if name not in self.processes:
                return {"status": "not_found"}
            
            proc_info = self.processes[name]
            proc = proc_info['process']
        
        try:
            # Check if process is still running