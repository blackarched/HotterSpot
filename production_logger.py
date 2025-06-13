#!/usr/bin/env python3
"""
Production-ready logging system for hotspot manager
Provides centralized logging with rotation, levels, and audit trails
"""

import logging
import logging.handlers
import os
import sys
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import threading

class ProductionLogger:
    """Centralized logging system with rotation and audit capabilities"""
    
    def __init__(self, log_dir: str = "/var/log/hotspot-manager", 
                 max_bytes: int = 10*1024*1024, backup_count: int = 5):
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._lock = threading.Lock()
        self._loggers = {}
        
        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up main logger
        self.main_logger = self._setup_logger("main", "hotspot-manager.log")
        self.error_logger = self._setup_logger("error", "errors.log", logging.ERROR)
        self.audit_logger = self._setup_logger("audit", "audit.log")
        self.security_logger = self._setup_logger("security", "security.log")
        
    def _setup_logger(self, name: str, filename: str, 
                     level: int = logging.INFO) -> logging.Logger:
        """Set up individual logger with rotation"""
        logger = logging.getLogger(f"hotspot.{name}")
        logger.setLevel(level)
        
        # Avoid duplicate handlers
        if logger.handlers:
            return logger
            
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / filename,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count
        )
        
        # Console handler for errors
        console_handler = logging.StreamHandler(sys.stdout)
        
        # Detailed formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        if level >= logging.WARNING:
            logger.addHandler(console_handler)
            
        return logger
    
    def info(self, message: str, component: str = "main", **kwargs):
        """Log info message"""
        self._log(logging.INFO, message, component, **kwargs)
    
    def warning(self, message: str, component: str = "main", **kwargs):
        """Log warning message"""
        self._log(logging.WARNING, message, component, **kwargs)
    
    def error(self, message: str, component: str = "main", exc_info: bool = False, **kwargs):
        """Log error message"""
        self._log(logging.ERROR, message, component, exc_info=exc_info, **kwargs)
        
    def critical(self, message: str, component: str = "main", exc_info: bool = True, **kwargs):
        """Log critical message"""
        self._log(logging.CRITICAL, message, component, exc_info=exc_info, **kwargs)
    
    def audit(self, action: str, user: str = "system", details: Dict[str, Any] = None, **kwargs):
        """Log audit event"""
        audit_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "user": user,
            "details": details or {},
            **kwargs
        }
        self.audit_logger.info(json.dumps(audit_data))
    
    def security(self, event: str, severity: str = "medium", 
                source_ip: str = None, details: Dict[str, Any] = None, **kwargs):
        """Log security event"""
        security_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "severity": severity,
            "source_ip": source_ip,
            "details": details or {},
            **kwargs
        }
        self.security_logger.warning(json.dumps(security_data))
    
    def _log(self, level: int, message: str, component: str, exc_info: bool = False, **kwargs):
        """Internal logging method"""
        logger = self._get_component_logger(component)
        
        # Add context information
        if kwargs:
            message = f"{message} | Context: {json.dumps(kwargs)}"
            
        if exc_info:
            logger.log(level, message, exc_info=True)
        else:
            logger.log(level, message)
            
        # Also log errors to error logger
        if level >= logging.ERROR:
            self.error_logger.log(level, f"[{component}] {message}", exc_info=exc_info)
    
    def _get_component_logger(self, component: str) -> logging.Logger:
        """Get or create component-specific logger"""
        if component not in self._loggers:
            self._loggers[component] = self._setup_logger(
                component, f"{component}.log"
            )
        return self._loggers[component]
    
    def log_exception(self, exc: Exception, component: str = "main", **kwargs):
        """Log exception with full traceback"""
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        exc_tb = traceback.format_exc()
        
        message = f"{exc_type}: {exc_msg}\nTraceback:\n{exc_tb}"
        self.error(message, component, **kwargs)
    
    def log_system_info(self):
        """Log system information at startup"""
        import platform
        import psutil
        
        system_info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "disk_usage": psutil.disk_usage('/').total
        }
        
        self.info("System startup", component="system", **system_info)
    
    def get_log_stats(self) -> Dict[str, Any]:
        """Get logging statistics"""
        stats = {}
        for log_file in self.log_dir.glob("*.log"):
            try:
                stat = log_file.stat()
                stats[log_file.name] = {
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            except OSError:
                continue
        return stats


class ExceptionHandler:
    """Global exception handler for production"""
    
    def __init__(self, logger: ProductionLogger):
        self.logger = logger
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.log_exception(exc_val, "exception_handler")
        return False  # Don't suppress exceptions
    
    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """Handle uncaught exceptions"""
        if issubclass(exc_type, KeyboardInterrupt):
            self.logger.info("Application interrupted by user")
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
            
        self.logger.critical(
            f"Uncaught exception: {exc_type.__name__}: {exc_value}",
            component="global",
            exc_info=(exc_type, exc_value, exc_traceback)
        )


# Global logger instance
_logger_instance = None
_logger_lock = threading.Lock()

def get_logger() -> ProductionLogger:
    """Get global logger instance (singleton)"""
    global _logger_instance
    if _logger_instance is None:
        with _logger_lock:
            if _logger_instance is None:
                _logger_instance = ProductionLogger()
                
                # Set up global exception handler
                handler = ExceptionHandler(_logger_instance)
                sys.excepthook = handler.handle_exception
                
                # Log system info at startup
                _logger_instance.log_system_info()
                
    return _logger_instance


# Convenience functions
def log_info(message: str, component: str = "main", **kwargs):
    get_logger().info(message, component, **kwargs)

def log_warning(message: str, component: str = "main", **kwargs):
    get_logger().warning(message, component, **kwargs)

def log_error(message: str, component: str = "main", exc_info: bool = False, **kwargs):
    get_logger().error(message, component, exc_info=exc_info, **kwargs)

def log_critical(message: str, component: str = "main", exc_info: bool = True, **kwargs):
    get_logger().critical(message, component, exc_info=exc_info, **kwargs)

def log_audit(action: str, user: str = "system", **kwargs):
    get_logger().audit(action, user, **kwargs)

def log_security(event: str, severity: str = "medium", **kwargs):
    get_logger().security(event, severity, **kwargs)


if __name__ == "__main__":
    # Test the logging system
    logger = get_logger()
    
    logger.info("Testing info log")
    logger.warning("Testing warning log")
    logger.error("Testing error log")
    
    logger.audit("test_action", "test_user", {"param": "value"})
    logger.security("test_security_event", "high", source_ip="127.0.0.1")
    
    # Test exception logging
    try:
        raise ValueError("Test exception")
    except Exception as e:
        logger.log_exception(e, "test")
    
    print("Log stats:", logger.get_log_stats())