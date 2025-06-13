#!/usr/bin/env python3
"""
DNS Server Module for Hotspot Tool
Provides DNS resolution and captive portal redirections
"""

import os
import sys
import socket
import struct
import threading
import time
import logging
from datetime import datetime

class DNSServer:
    def __init__(self, config_manager, captive_portal=None):
        self.config_manager = config_manager
        self.captive_portal = captive_portal
        self.socket = None
        self.running = False
        self.server_thread = None
        
        # DNS configuration
        self.dns_port = 53
        self.captive_portal_ip = "192.168.4.1"  # Default hotspot gateway IP
        self.upstream_dns = ["8.8.8.8", "8.8.4.4"]  # Google DNS as fallback
        
        # Blocked domains for security
        self.blocked_domains = {
            'malware.com', 'phishing.com', 'spam.com'
        }
        
        # DNS cache
        self.dns_cache = {}
        self.cache_ttl = 300  # 5 minutes
    
    def start_server(self, interface_ip=None):
        """Start the DNS server"""
        if self.running:
            return False
        
        try:
            if interface_ip:
                self.captive_portal_ip = interface_ip
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('', self.dns_port))
            
            self.running = True
            self.server_thread = threading.Thread(target=self._dns_server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            logging.info(f"DNS server started on port {self.dns_port}")
            return True
        except Exception as e:
            logging.error(f"Failed to start DNS server: {e}")
            return False
    
    def stop_server(self):
        """Stop the DNS server"""
        if not self.running:
            return False
        
        try:
            self.running = False
            if self.socket:
                self.socket.close()
            
            if self.server_thread:
                self.server_thread.join(timeout=5)
            
            logging.info("DNS server stopped")
            return True
        except Exception as e:
            logging.error(f"Failed to stop DNS server: {e}")
            return False
    
    def _dns_server_loop(self):
        """Main DNS server loop"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                threading.Thread(target=self._handle_dns_request, 
                               args=(data, addr)).start()
            except Exception as e:
                if self.running:
                    logging.error(f"DNS server error: {e}")
                break
    
    def _handle_dns_request(self, data, addr):
        """Handle incoming DNS request"""
        try:
            # Parse DNS query
            query_info = self._parse_dns_query(data)
            if not query_info:
                return
            
            domain, query_type = query_info
            client_ip = addr[0]
            
            logging.debug(f"DNS query from {client_ip}: {domain} ({query_type})")
            
            # Check if client is authenticated (if captive portal is enabled)
            if self.captive_portal and not self._is_client_authenticated(client_ip):
                # Redirect to captive portal
                response = self._create_dns_response(data, domain, self.captive_portal_ip)
            elif domain.lower() in self.blocked_domains:
                # Block malicious domains
                response = self._create_dns_response(data, domain, "0.0.0.0")
                logging.warning(f"Blocked access to {domain} from {client_ip}")
            else:
                # Check cache first
                cache_key = f"{domain}:{query_type}"
                if cache_key in self.dns_cache:
                    cache_entry = self.dns_cache[cache_key]
                    if time.time() - cache_entry['timestamp'] < self.cache_ttl:
                        response = self._create_dns_response(data, domain, cache_entry['ip'])
                    else:
                        # Cache expired
                        del self.dns_cache[cache_key]
                        response = self._forward_dns_query(data, domain)
                else:
                    # Forward to upstream DNS
                    response = self._forward_dns_query(data, domain)
            
            # Send response
            if response:
                self.socket.sendto(response, addr)
            
        except Exception as e:
            logging.error(f"Error handling DNS request: {e}")
    
    def _parse_dns_query(self, data):
        """Parse DNS query packet"""
        try:
            if len(data) < 12:
                return None
            
            # Skip DNS header (12 bytes)
            offset = 12
            
            # Parse domain name
            domain_parts = []
            while offset < len(data):
                length = data[offset]
                if length == 0:
                    offset += 1
                    break
                if length > 63:
                    return None  # Invalid domain name
                
                offset += 1
                if offset + length > len(data):
                    return None
                
                domain_parts.append(data[offset:offset + length].decode('utf-8'))
                offset += length
            
            domain = '.'.join(domain_parts)
            
            # Parse query type
            if offset + 4 > len(data):
                return None
            
            query_type = struct.unpack('!H', data[offset:offset + 2])[0]
            
            return domain, query_type
            
        except Exception as e:
            logging.error(f"Error parsing DNS query: {e}")
            return None
    
    def _create_dns_response(self, original_query, domain, ip_address):
        """Create DNS response packet"""
        try:
            # DNS header (modify original query header)
            response = bytearray(original_query)
            
            # Set response flags
            response[2] = 0x81  # Standard query response, no error
            response[3] = 0x80  # Recursion available
            
            # Answer count
            response[6] = 0x00
            response[7] = 0x01
            
            # Add answer section
            answer = bytearray()
            
            # Name (pointer to query name)
            answer.extend([0xc0, 0x0c])
            
            # Type (A record)
            answer.extend(struct.pack('!H', 1))
            
            # Class (IN)
            answer.extend(struct.pack('!H', 1))
            
            # TTL (300 seconds)
            answer.extend(struct.pack('!I', 300))
            
            # Data length (4 bytes for IPv4)
            answer.extend(struct.pack('!H', 4))
            
            # IP address
            ip_parts = ip_address.split('.')
            answer.extend([int(part) for part in ip_parts])
            
            response.extend(answer)
            
            return bytes(response)
            
        except Exception as e:
            logging.error(f"Error creating DNS response: {e}")
            return None
    
    def _forward_dns_query(self, query_data, domain):
        """Forward DNS query to upstream servers"""
        for dns_server in self.upstream_dns:
            try:
                # Create socket for upstream query
                upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                upstream_socket.settimeout(5)
                
                # Send query to upstream DNS
                upstream_socket.sendto(query_data, (dns_server, 53))
                response, _ = upstream_socket.recvfrom(1024)
                upstream_socket.close()
                
                # Cache the response
                ip_address = self._extract_ip_from_response(response)
                if ip_address:
                    cache_key = f"{domain}:1"  # A record
                    self.dns_cache[cache_key] = {
                        'ip': ip_address,
                        'timestamp': time.time()
                    }
                
                return response
                
            except Exception as e:
                logging.warning(f"Failed to query DNS server {dns_server}: {e}")
                continue
        
        # If all upstream servers fail, return None
        logging.error(f"All upstream DNS servers failed for query: {domain}")
        return None
    
    def _extract_ip_from_response(self, response_data):
        """Extract IP address from DNS response"""
        try:
            if len(response_data) < 12:
                return None
            
            # Check if response has answers
            answer_count = struct.unpack('!H', response_data[6:8])[0]
            if answer_count == 0:
                return None
            
            # Skip header and question section
            offset = 12
            
            # Skip question section
            while offset < len(response_data):
                length = response_data[offset]
                if length == 0:
                    offset += 5  # Skip null terminator and type/class
                    break
                offset += length + 1
            
            # Parse answer section
            if offset + 12 <= len(response_data):
                # Skip name pointer and type/class/ttl
                offset += 10
                
                # Data length
                data_length = struct.unpack('!H', response_data[offset:offset + 2])[0]
                offset += 2
                
                # Extract IP address (for A records)
                if data_length == 4:
                    ip_bytes = response_data[offset:offset + 4]
                    return '.'.join(str(b) for b in ip_bytes)
            
            return None
            
        except Exception as e:
            logging.error(f"Error extracting IP from DNS response: {e}")
            return None
    
    def _is_client_authenticated(self, client_ip):
        """Check if client is authenticated through captive portal"""
        if not self.captive_portal:
            return True
        
        try:
            mac_address = self.captive_portal.get_mac_from_ip(client_ip)
            return self.captive_portal.is_authenticated(mac_address)
        except Exception as e:
            logging.error(f"Error checking client authentication: {e}")
            return False
    
    def add_blocked_domain(self, domain):
        """Add domain to blocked list"""
        self.blocked_domains.add(domain.lower())
        logging.info(f"Added {domain} to blocked domains")
    
    def remove_blocked_domain(self, domain):
        """Remove domain from blocked list"""
        self.blocked_domains.discard(domain.lower())
        logging.info(f"Removed {domain} from blocked domains")
    
    def clear_cache(self):
        """Clear DNS cache"""
        self.dns_cache.clear()
        logging.info("DNS cache cleared")
    
    def get_stats(self):
        """Get DNS server statistics"""
        return {
            'running': self.running,
            'cache_entries': len(self.dns_cache),
            'blocked_domains': len(self.blocked_domains),
            'upstream_servers': self.upstream_dns
        }
    
    def set_upstream_dns(self, dns_servers):
        """Set upstream DNS servers"""
        if isinstance(dns_servers, str):
            dns_servers = [dns_servers]
        
        self.upstream_dns = dns_servers
        logging.info(f"Updated upstream DNS servers: {dns_servers}")

if __name__ == "__main__":
    # Test the DNS server
    logging.basicConfig(level=logging.DEBUG)
    
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from config_manager import ConfigManager
    
    config_manager = ConfigManager()
    dns_server = DNSServer(config_manager)
    
    if dns_server.start_server():
        print("DNS server started on port 53")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            dns_server.stop_server()
            print("\nDNS server stopped")
    else:
        print("Failed to start DNS server")
