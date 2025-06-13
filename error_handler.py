#!/usr/bin/env python3
"""
Comprehensive error handling and recovery system for hotspot manager
Handles network failures, permission issues, and system recovery
"""

import subprocess
import time
import threading
import signal
import os
import sys
from typing import Dict, Any, Optional, Callable, List
from functools import wraps
import psutil
from dataclasses import dataclass
from enum import Enum
from production_logger import get_logger

class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"  
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    NETWORK = "network"
    PERMISSION = "permission"
    SYSTEM = "system"
    CONFIG = "config"
    RESOURCE = "resource"
    USER = "user"

@dataclass
class ErrorContext:
    category: ErrorCategory
    severity: ErrorSeverity
    component: str
    operation: str
    details: Dict[str, Any]
    timestamp: float
    retry_count: int = 0

class HotspotError(Exception):
    """Base exception for hotspot operations"""
    def __init__(self, message: str, context: ErrorContext):
        super().__init__(message)
        self.context = context

class NetworkError(HotspotError):
    """Network-related errors"""
    pass

class PermissionError(HotspotError):
    """Permission-related errors"""
    pass

class SystemError(HotspotError):
    """System-related errors"""
    pass

class ConfigError(HotspotError):
    """Configuration errors"""
    pass

class ResourceError(HotspotError):
    """Resource exhaustion errors"""
    pass

class ErrorHandler:
    """Comprehensive error handling and recovery system"""
    
    def __init__(self):
        self.logger = get_logger()
        self.recovery_strategies = {}
        self.error_counts = {}
        self.circuit_breakers = {}
        self.shutdown_handlers = []
        self._lock = threading.Lock()
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Register default recovery strategies
        self._register_default_strategies()
    
    def _register_default_strategies(self):
        """Register default error recovery strategies"""
        
        # Network recovery strategies
        self.register_recovery(
            ErrorCategory.NETWORK, 
            "interface_down",
            self._recover_network_interface
        )
        
        self.register_recovery(
            ErrorCategory.NETWORK,
            "connection_failed", 
            self._recover_connection
        )
        
        # Permission recovery strategies
        self.register_recovery(
            ErrorCategory.PERMISSION,
            "access_denied",
            self._recover_permissions
        )
        
        # System recovery strategies
        self.register_recovery(
            ErrorCategory.SYSTEM,
            "service_failed",
            self._recover_service
        )
        
        # Resource recovery strategies
        self.register_recovery(
            ErrorCategory.RESOURCE,
            "memory_exhausted",
            self._recover_resources
        )
    
    def register_recovery(self, category: ErrorCategory, operation: str, 
                         strategy: Callable[[ErrorContext], bool]):
        """Register error recovery strategy"""
        key = f"{category.value}:{operation}"
        self.recovery_strategies[key] = strategy
        
    def register_shutdown_handler(self, handler: Callable[[], None]):
        """Register cleanup handler for shutdown"""
        self.shutdown_handlers.append(handler)
    
    def handle_error(self, error: Exception, context: ErrorContext) -> bool:
        """Handle error with recovery attempt"""
        
        # Log the error
        self.logger.error(
            f"Error in {context.component}.{context.operation}: {str(error)}",
            component=context.component,
            error_category=context.category.value,
            severity=context.severity.value,
            details=context.details,
            exc_info=True
        )
        
        # Update error counts
        error_key = f"{context.component}:{context.operation}"
        with self._lock:
            self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Check circuit breaker
        if self._check_circuit_breaker(error_key):
            self.logger.critical(
                f"Circuit breaker open for {error_key}",
                component="error_handler"
            )
            return False
        
        # Attempt recovery
        recovery_key = f"{context.category.value}:{context.operation}"
        if recovery_key in self.recovery_strategies:
            try:
                success = self.recovery_strategies[recovery_key](context)
                if success:
                    self.logger.info(
                        f"Recovery successful for {error_key}",
                        component="error_handler"
                    )
                    # Reset error count on successful recovery
                    with self._lock:
                        self.error_counts[error_key] = 0
                    return True
                else:
                    self.logger.warning(
                        f"Recovery failed for {error_key}",
                        component="error_handler"
                    )
            except Exception as recovery_error:
                self.logger.error(
                    f"Recovery strategy failed: {str(recovery_error)}",
                    component="error_handler",
                    exc_info=True
                )
        
        # Log security event for critical errors
        if context.severity == ErrorSeverity.CRITICAL:
            self.logger.security(
                "critical_system_error",
                "high",
                details={"component": context.component, "operation": context.operation}
            )
        
        return False
    
    def _check_circuit_breaker(self, error_key: str) -> bool:
        """Check if circuit breaker should be opened"""
        error_count = self.error_counts.get(error_key, 0)
        threshold = 5  # Open circuit after 5 consecutive errors
        
        if error_count >= threshold:
            if error_key not in self.circuit_breakers:
                self.circuit_breakers[error_key] = time.time()
                return True
            
            # Reset circuit breaker after 5 minutes
            if time.time() - self.circuit_breakers[error_key] > 300:
                del self.circuit_breakers[error_key]
                self.error_counts[error_key] = 0
                return False
            
            return True
        
        return False
    
    def _recover_network_interface(self, context: ErrorContext) -> bool:
        """Recover network interface"""
        interface = context.details.get('interface')
        if not interface:
            return False
        
        try:
            # Try to bring interface up
            result = subprocess.run(
                ['ip', 'link', 'set', interface, 'up'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                time.sleep(2)  # Wait for interface to come up
                return True
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        
        return False
    
    def _recover_connection(self, context: ErrorContext) -> bool:
        """Recover network connection"""
        try:
            # Restart NetworkManager service
            result = subprocess.run(
                ['systemctl', 'restart', 'NetworkManager'],
                capture_output=True, text=True, timeout=30
            )
            
            if result.returncode == 0:
                time.sleep(5)  # Wait for service restart
                return True
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
        
        return False
    
    def _recover_permissions(self, context: ErrorContext) -> bool:
        """Recover from permission errors"""
        # Check if running as root
        if os.geteuid() != 0:
            self.logger.error(
                "Permission denied - application must run as root",
                component="error_handler"
            )
            return False
        
        # Try to fix common permission issues
        files_to_fix = [
            "/etc/NetworkManager/system-connections/",
            "/var/lib/dhcp/",
            "/var/log/hotspot-manager/"
        ]
        
        for path in files_to_fix:
            try:
                if os.path.exists(path):
                    os.chmod(path, 0o755)
            except OSError:
                continue
        
        return True
    
    def _recover_service(self, context: ErrorContext) -> bool:
        """Recover failed service"""
        service = context.details.get('service')
        if not service:
            return False
        
        try:
            # Restart the service
            result = subprocess.run(
                ['systemctl', 'restart', service],
                capture_output=True, text=True, timeout=30
            )
            
            return result.returncode == 0
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False
    
    def _recover_resources(self, context: ErrorContext) -> bool:
        """Recover from resource exhaustion"""
        try:
            # Force garbage collection
            import gc
            gc.collect()
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                self.logger.warning(
                    f"High memory usage: {memory.percent}%",
                    component="error_handler"
                )
                # Could implement more aggressive cleanup here
            
            return True
            
        except Exception:
            return False
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(
            f"Received signal {signum}, initiating shutdown",
            component="error_handler"
        )
        
        # Run shutdown handlers
        for handler in self.shutdown_handlers:
            try:
                handler()
            except Exception as e:
                self.logger.error(
                    f"Shutdown handler failed: {str(e)}",
                    component="error_handler",
                    exc_info=True
                )
        
        sys.exit(0)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return {
            "error_counts": self.error_counts.copy(),
            "circuit_breakers": {
                key: time.time() - timestamp 
                for key, timestamp in self.circuit_breakers.items()
            }
        }


def with_error_handling(category: ErrorCategory, operation: str, 
                       severity: ErrorSeverity = ErrorSeverity.MEDIUM,
                       max_retries: int = 3, retry_delay: float = 1.0):
    """Decorator for automatic error handling and retry"""
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            error_handler = get_error_handler()
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except Exception as e:
                    context = ErrorContext(
                        category=category,
                        severity=severity,
                        component=func.__module__,
                        operation=operation,
                        details={
                            "function": func.__name__,
                            "args": str(args)[:200],  # Truncate long args
                            "attempt": attempt + 1
                        },
                        timestamp=time.time(),
                        retry_count=attempt
                    )
                    
                    if attempt == max_retries:
                        # Final attempt failed
                        error_handler.handle_error(e, context)
                        raise
                    
                    # Try recovery
                    recovered = error_handler.handle_error(e, context)
                    
                    if not recovered and attempt < max_retries:
                        time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    elif recovered:
                        continue  # Retry immediately after successful recovery
            
        return wrapper
    return decorator


# Global error handler instance
_error_handler_instance = None
_error_handler_lock = threading.Lock()

def get_error_handler() -> ErrorHandler:
    """Get global error handler instance (singleton)"""
    global _error_handler_instance
    if _error_handler_instance is None:
        with _error_handler_lock:
            if _error_handler_instance is None:
                _error_handler_instance = ErrorHandler()
    return _error_handler_instance


def safe_execute(func: Callable, *args, category: ErrorCategory = ErrorCategory.SYSTEM,
                operation: str = "unknown", **kwargs) -> Optional[Any]:
    """Safely execute function with error handling"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        context = ErrorContext(
            category=category,
            severity=ErrorSeverity.MEDIUM,
            component=func.__module__ if hasattr(func, '__module__') else "unknown",
            operation=operation,
            details={"function": getattr(func, '__name__', 'anonymous')},
            timestamp=time.time()
        )
        
        get_error_handler().handle_error(e, context)
        return None


if __name__ == "__main__":
    # Test error handling
    handler = get_error_handler()
    
    # Test with decorator
    @with_error_handling(ErrorCategory.NETWORK, "test_operation")
    def test_function():
        raise NetworkError(
            "Test error",
            ErrorContext(
                ErrorCategory.NETWORK,
                ErrorSeverity.MEDIUM,
                "test",
                "test_operation",
                {},
                time.time()
            )
        )
    
    try:
        test_function()
    except Exception as e:
        print(f"Caught: {e}")
    
    print("Error stats:", handler.get_error_stats())