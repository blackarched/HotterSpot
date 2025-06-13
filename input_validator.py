#!/usr/bin/env python3
"""
Input validation and security system for hotspot manager
Sanitizes all user inputs and enforces security policies
"""

import re
import ipaddress
import hashlib
import secrets
import string
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import dataclass
from enum import Enum
import json
from production_logger import get_logger

class ValidationError(Exception):
    """Validation error exception"""
    pass

class SecurityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ValidationRule:
    name: str
    pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_chars: Optional[str] = None
    forbidden_chars: Optional[str] = None
    custom_validator: Optional[callable] = None
    security_level: SecurityLevel = SecurityLevel.MEDIUM

class InputValidator:
    """Comprehensive input validation and sanitization"""
    
    def __init__(self):
        self.logger = get_logger()
        self.rules = {}
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Set up default validation rules"""
        
        # SSID validation
        self.rules['ssid'] = ValidationRule(
            name='ssid',
            min_length=1,
            max_length=32,
            forbidden_chars='\x00\n\r\t',
            security_level=SecurityLevel.MEDIUM
        )
        
        # Password validation
        self.rules['password'] = ValidationRule(
            name='password',
            min_length=8,
            max_length=63,
            custom_validator=self._validate_password,
            security_level=SecurityLevel.HIGH
        )
        
        # IP address validation
        self.rules['ip_address'] = ValidationRule(
            name='ip_address',
            custom_validator=self._validate_ip_address,
            security_level=SecurityLevel.MEDIUM
        )
        
        # MAC address validation
        self.rules['mac_address'] = ValidationRule(
            name='mac_address',
            pattern=r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$',
            security_level=SecurityLevel.MEDIUM
        )
        
        # Interface name validation
        self.rules['interface'] = ValidationRule(
            name='interface',
            pattern=r'^[a-zA-Z0-9_-]+$',
            min_length=1,
            max_length=15,
            security_level=SecurityLevel.MEDIUM
        )
        
        # Port validation
        self.rules['port'] = ValidationRule(
            name='port',
            custom_validator=self._validate_port,
            security_level=SecurityLevel.MEDIUM
        )
        
        # Filename validation
        self.rules['filename'] = ValidationRule(
            name='filename',
            pattern=r'^[a-zA-Z0-9._-]+$',
            min_length=1,
            max_length=255,
            forbidden_chars='/',
            security_level=SecurityLevel.HIGH
        )
        
        # User input validation (for forms, etc.)
        self.rules['user_input'] = ValidationRule(
            name='user_input',
            max_length=1000,
            forbidden_chars='\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f',
            custom_validator=self._validate_user_input,
            security_level=SecurityLevel.MEDIUM
        )
        
        # Command validation (for system commands)
        self.rules['command'] = ValidationRule(
            name='command',
            pattern=r'^[a-zA-Z0-9\s._/-]+$',
            max_length=200,
            custom_validator=self._validate_command,
            security_level=SecurityLevel.CRITICAL
        )
    
    def validate(self, value: Any, rule_name: str, context: str = "") -> Any:
        """Validate input against specified rule"""
        if rule_name not in self.rules:
            raise ValidationError(f"Unknown validation rule: {rule_name}")
        
        rule = self.rules[rule_name]
        
        # Convert to string if needed
        if not isinstance(value, str) and value is not None:
            value = str(value)
        
        # Check for None/empty
        if value is None or value == "":
            if rule.min_length and rule.min_length > 0:
                raise ValidationError(f"{rule.name} cannot be empty")
            return value
        
        # Length validation
        if rule.min_length and len(value) < rule.min_length:
            raise ValidationError(f"{rule.name} must be at least {rule.min_length} characters")
        
        if rule.max_length and len(value) > rule.max_length:
            raise ValidationError(f"{rule.name} cannot exceed {rule.max_length} characters")
        
        # Character validation
        if rule.forbidden_chars:
            for char in rule.forbidden_chars:
                if char in value:
                    raise ValidationError(f"{rule.name} contains forbidden character: {repr(char)}")
        
        if rule.allowed_chars:
            for char in value:
                if char not in rule.allowed_chars:
                    raise ValidationError(f"{rule.name} contains invalid character: {repr(char)}")
        
        # Pattern validation
        if rule.pattern and not re.match(rule.pattern, value):
            raise ValidationError(f"{rule.name} format is invalid")
        
        # Custom validation
        if rule.custom_validator:
            try:
                value = rule.custom_validator(value)
            except Exception as e:
                raise ValidationError(f"{rule.name} validation failed: {str(e)}")
        
        # Log security validation
        if rule.security_level in [SecurityLevel.HIGH, SecurityLevel.CRITICAL]:
            self.logger.security(
                "input_validation",
                rule.security_level.value,
                details={
                    "rule": rule_name,
                    "context": context,
                    "length": len(value) if value else 0
                }
            )
        
        return value
    
    def _validate_password(self, password: str) -> str:
        """Validate password strength"""
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters")
        
        # Check for common weak passwords
        weak_passwords = [
            'password', '12345678', 'admin123', 'qwerty123',
            'password123', 'admin', 'root', 'guest'
        ]
        
        if password.lower() in weak_passwords:
            raise ValidationError("Password is too common and weak")
        
        # Check character complexity
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
        
        complexity_count = sum([has_upper, has_lower, has_digit, has_special])
        
        if complexity_count < 3:
            raise ValidationError("Password must contain at least 3 of: uppercase, lowercase, numbers, special characters")
        
        return password
    
    def _validate_ip_address(self, ip: str) -> str:
        """Validate IP address"""
        try:
            # Try IPv4 first
            ipaddress.IPv4Address(ip)
            return ip
        except ipaddress.AddressValueError:
            try:
                # Try IPv6
                ipaddress.IPv6Address(ip)
                return ip
            except ipaddress.AddressValueError:
                raise ValidationError("Invalid IP address format")
    
    def _validate_port(self, port: Union[str, int]) -> int:
        """Validate port number"""
        try:
            port_num = int(port)
            if not (1 <= port_num <= 65535):
                raise ValidationError("Port must be between 1 and 65535")
            return port_num
        except ValueError:
            raise ValidationError("Port must be a valid number")
    
    def _validate_user_input(self, input_text: str) -> str:
        """Validate general user input for XSS and injection attacks"""
        # Check for potential XSS patterns
        xss_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]
        
        input_lower = input_text.lower()
        for pattern in xss_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE | re.DOTALL):
                raise ValidationError("Input contains potentially malicious content")
        
        # Check for SQL injection patterns
        sql_patterns = [
            r'(\s|^)(union|select|insert|update|delete|drop|create|alter)\s',
            r'(\s|^)(exec|execute|sp_)\s',
            r'(\s|^)(xp_|sp_oa)\w+',
            r';\s*(drop|delete|insert|update)',
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                raise ValidationError("Input contains SQL injection patterns")
        
        return input_text
    
    def _validate_command(self, command: str) -> str:
        """Validate system command for security"""
        # Blacklist dangerous commands
        dangerous_commands = [
            'rm', 'del', 'format', 'fdisk', 'mkfs',
            'dd', 'chmod 777', 'chown', 'su', 'sudo',
            'passwd', 'useradd', 'userdel', 'usermod',
            'shutdown', 'reboot', 'halt', 'init',
            'kill', 'killall', 'pkill',
            '&&', '||', ';', '|', '>', '>>', '<',
            '$(', '`', 'eval', 'exec'
        ]
        
        command_lower = command.lower()
        for dangerous in dangerous_commands:
            if dangerous in command_lower:
                raise ValidationError(f"Command contains dangerous element: {dangerous}")
        
        return command
    
    def sanitize_for_html(self, text: str) -> str:
        """Sanitize text for HTML output"""
        if not text:
            return ""
        
        # HTML entity encoding
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;'
        }
        
        for char, entity in replacements.items():
            text = text.replace(char, entity)
        
        return text
    
    def sanitize_for_shell(self, text: str) -> str:
        """Sanitize text for shell command usage"""
        if not text:
            return ""
        
        # Remove or escape dangerous characters
        dangerous_chars = [', '`', ';', '&', '|', '>', '<', '\n', '\r']
        for char in dangerous_chars:
            text = text.replace(char, '')
        
        # Add quotes if contains spaces
        if ' ' in text:
            text = f'"{text}"'
        
        return text
    
    def validate_json(self, json_str: str, max_depth: int = 10) -> Dict:
        """Validate and parse JSON with security checks"""
        try:
            # Check JSON size
            if len(json_str) > 100000:  # 100KB limit
                raise ValidationError("JSON data too large")
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Check nesting depth
            def check_depth(obj, current_depth=0):
                if current_depth > max_depth:
                    raise ValidationError("JSON nesting too deep")
                
                if isinstance(obj, dict):
                    for value in obj.values():
                        check_depth(value, current_depth + 1)
                elif isinstance(obj, list):
                    for item in obj:
                        check_depth(item, current_depth + 1)
            
            check_depth(data)
            return data
            
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format: {str(e)}")
    
    def validate_batch(self, data: Dict[str, Any], rules: Dict[str, str], 
                      context: str = "") -> Dict[str, Any]:
        """Validate multiple inputs at once"""
        validated_data = {}
        errors = []
        
        for field, value in data.items():
            if field in rules:
                try:
                    validated_data[field] = self.validate(value, rules[field], context)
                except ValidationError as e:
                    errors.append(f"{field}: {str(e)}")
            else:
                # Default validation for unknown fields
                try:
                    validated_data[field] = self.validate(value, 'user_input', context)
                except ValidationError as e:
                    errors.append(f"{field}: {str(e)}")
        
        if errors:
            raise ValidationError(f"Validation errors: {'; '.join(errors)}")
        
        return validated_data


class SecurityPolicy:
    """Security policy enforcement"""
    
    def __init__(self):
        self.logger = get_logger()
        self.failed_attempts = {}
        self.blocked_ips = set()
        self.rate_limits = {}
    
    def check_rate_limit(self, identifier: str, max_requests: int = 10, 
                        window_seconds: int = 60) -> bool:
        """Check rate limiting"""
        import time
        
        current_time = time.time()
        
        if identifier not in self.rate_limits:
            self.rate_limits[identifier] = []
        
        # Clean old requests
        self.rate_limits[identifier] = [
            req_time for req_time in self.rate_limits[identifier]
            if current_time - req_time < window_seconds
        ]
        
        # Check limit
        if len(self.rate_limits[identifier]) >= max_requests:
            self.logger.security(
                "rate_limit_exceeded",
                "medium",
                details={"identifier": identifier, "requests": len(self.rate_limits[identifier])}
            )
            return False
        
        # Add current request
        self.rate_limits[identifier].append(current_time)
        return True
    
    def record_failed_attempt(self, identifier: str, max_attempts: int = 5):
        """Record failed authentication attempt"""
        if identifier not in self.failed_attempts:
            self.failed_attempts[identifier] = 0
        
        self.failed_attempts[identifier] += 1
        
        if self.failed_attempts[identifier] >= max_attempts:
            self.blocked_ips.add(identifier)
            self.logger.security(
                "ip_blocked_multiple_failures",
                "high",
                details={"identifier": identifier, "attempts": self.failed_attempts[identifier]}
            )
    
    def is_blocked(self, identifier: str) -> bool:
        """Check if identifier is blocked"""
        return identifier in self.blocked_ips
    
    def clear_failed_attempts(self, identifier: str):
        """Clear failed attempts for identifier"""
        if identifier in self.failed_attempts:
            del self.failed_attempts[identifier]
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate cryptographically secure token"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """Hash password with salt"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Use PBKDF2 with SHA-256
        import hashlib
        hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return hashed.hex(), salt
    
    def verify_password(self, password: str, hashed: str, salt: str) -> bool:
        """Verify password against hash"""
        expected_hash, _ = self.hash_password(password, salt)
        return secrets.compare_digest(expected_hash, hashed)


# Global instances
_validator_instance = None
_security_policy_instance = None

def get_validator() -> InputValidator:
    """Get global validator instance"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = InputValidator()
    return _validator_instance

def get_security_policy() -> SecurityPolicy:
    """Get global security policy instance"""
    global _security_policy_instance
    if _security_policy_instance is None:
        _security_policy_instance = SecurityPolicy()
    return _security_policy_instance

# Convenience functions
def validate_input(value: Any, rule: str, context: str = "") -> Any:
    """Validate single input"""
    return get_validator().validate(value, rule, context)

def validate_inputs(data: Dict[str, Any], rules: Dict[str, str], context: str = "") -> Dict[str, Any]:
    """Validate multiple inputs"""
    return get_validator().validate_batch(data, rules, context)

def sanitize_html(text: str) -> str:
    """Sanitize text for HTML"""
    return get_validator().sanitize_for_html(text)

def sanitize_shell(text: str) -> str:
    """Sanitize text for shell"""
    return get_validator().sanitize_for_shell(text)


if __name__ == "__main__":
    # Test validation system
    validator = get_validator()
    security = get_security_policy()
    
    # Test SSID validation
    try:
        ssid = validator.validate("MyHotspot", "ssid")
        print(f"Valid SSID: {ssid}")
    except ValidationError as e:
        print(f"SSID Error: {e}")
    
    # Test password validation
    try:
        password = validator.validate("SecurePass123!", "password")
        print("Password valid")
    except ValidationError as e:
        print(f"Password Error: {e}")
    
    # Test batch validation
    data = {
        "ssid": "TestNetwork",
        "password": "StrongPassword123!",
        "ip": "192.168.1.1"
    }
    rules = {
        "ssid": "ssid",
        "password": "password", 
        "ip": "ip_address"
    }
    
    try:
        validated = validator.validate_batch(data, rules)
        print(f"Batch validation passed: {validated}")
    except ValidationError as e:
        print(f"Batch Error: {e}")
    
    # Test security policy
    token = security.generate_secure_token()
    print(f"Secure token: {token}")
    
    hashed, salt = security.hash_password("testpassword")
    print(f"Password hashed successfully")
    
    verified = security.verify_password("testpassword", hashed, salt)
    print(f"Password verification: {verified}")