#!/usr/bin/env python3
"""
DHCP Server Module for Hotspot Tool
Provides IP address assignment and network configuration to clients
"""

import os
import sys
import socket
import struct
import threading
import time
import logging
import random
from datetime import datetime, timedelta

class DHCPServer:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.socket = None
        self.running = False
        self.server_thread = None
        
        # DHCP Configuration
        self.server_ip = "192.168.4.1"
        self.subnet_mask = "255.255.255.0"
        self.gateway = "192.168.4.1"
        self.dns_servers = ["192.168.4.1", "8.8.8.8"]
        self.lease_time = 3600  # 1 hour
        self.ip_pool_start = "192.168.4.10"
        self.ip_pool_end = "192.168.4.100"
        
        # DHCP State
        self.leases = {}  # MAC -> lease info
        self.ip_assignments = {}  # IP -> MAC
        self.available_ips = self._generate_ip_pool()
        
        # DHCP Message Types
        self.DHCP_DISCOVER = 1
        self.DHCP_OFFER = 2
        self.DHCP_REQUEST = 3
        self.DHCP_DECLINE = 4
        self.DHCP_ACK = 5
        self.DHCP_NAK = 6
        self.DHCP_RELEASE = 7
        self.DHCP_INFORM = 8
    
    def _generate_ip_pool(self):
        """Generate available IP addresses in the pool"""
        start_parts = self.ip_pool_start.split('.')
        end_parts = self.ip_pool_end.split('.')
        
        start_num = int(start_parts[3])
        end_num = int(end_parts[3])
        base = '.'.join(start_parts[:3])
        
        return [f"{base}.{i}" for i in range(start_num, end_num + 1)]
    
    def start_server(self, interface_ip=None):
        """Start the DHCP server"""
        if self.running:
            return False
        
        try:
            if interface_ip:
                self.server_ip = interface_ip
                self.gateway = interface_ip
                self.dns_servers[0] = interface_ip
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.socket.bind(('', 67))  # DHCP server port
            
            self.running = True
            self.server_thread = threading.Thread(target=self._dhcp_server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            logging.info(f"DHCP server started on port 67")
            return True
        except Exception as e:
            logging.error(f"Failed to start DHCP server: {e}")
            return False
    
    def stop_server(self):
        """Stop the DHCP server"""
        if not self.running:
            return False
        
        try:
            self.running = False
            if self.socket:
                self.socket.close()
            
            if self.server_thread:
                self.server_thread.join(timeout=5)
            
            logging.info("DHCP server stopped")
            return True
        except Exception as e:
            logging.error(f"Failed to stop DHCP server: {e}")
            return False
    
    def _dhcp_server_loop(self):
        """Main DHCP server loop"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                threading.Thread(target=self._handle_dhcp_request, 
                               args=(data, addr)).start()
            except Exception as e:
                if self.running:
                    logging.error(f"DHCP server error: {e}")
                break
    
    def _handle_dhcp_request(self, data, addr):
        """Handle incoming DHCP request"""
        try:
            dhcp_packet = self._parse_dhcp_packet(data)
            if not dhcp_packet:
                return
            
            client_mac = dhcp_packet['chaddr']
            message_type = dhcp_packet.get('message_type')
            
            logging.debug(f"DHCP {self._get_message_type_name(message_type)} from {client_mac}")
            
            if message_type == self.DHCP_DISCOVER:
                self._handle_discover(dhcp_packet, addr)
            elif message_type == self.DHCP_REQUEST:
                self._handle_request(dhcp_packet, addr)
            elif message_type == self.DHCP_RELEASE:
                self._handle_release(dhcp_packet, addr)
            elif message_type == self.DHCP_DECLINE:
                self._handle_decline(dhcp_packet, addr)
            
        except Exception as e:
            logging.error(f"Error handling DHCP request: {e}")
    
    def _parse_dhcp_packet(self, data):
        """Parse DHCP packet"""
        try:
            if len(data) < 240:
                return None
            
            # Parse DHCP header
            packet = {}
            packet['op'] = data[0]
            packet['htype'] = data[1]
            packet['hlen'] = data[2]
            packet['hops'] = data[3]
            packet['xid'] = struct.unpack('!I', data[4:8])[0]
            packet['secs'] = struct.unpack('!H', data[8:10])[0]
            packet['flags'] = struct.unpack('!H', data[10:12])[0]
            packet['ciaddr'] = socket.inet_ntoa(data[12:16])
            packet['yiaddr'] = socket.inet_ntoa(data[16:20])
            packet['siaddr'] = socket.inet_ntoa(data[20:24])
            packet['giaddr'] = socket.inet_ntoa(data[24:28])
            
            # Extract MAC address
            chaddr = data[28:44]
            packet['chaddr'] = ':'.join([f'{b:02x}' for b in chaddr[:packet['hlen']]])
            
            # Parse options
            options_start = 240
            if len(data) > options_start + 4:
                # Check magic cookie
                magic_cookie = data[options_start:options_start + 4]
                if magic_cookie == b'\x63\x82\x53\x63':
                    packet.update(self._parse_dhcp_options(data[options_start + 4:]))
            
            return packet
            
        except Exception as e:
            logging.error(f"Error parsing DHCP packet: {e}")
            return None
    
    def _parse_dhcp_options(self, options_data):
        """Parse DHCP options"""
        options = {}
        i = 0
        
        while i < len(options_data):
            if options_data[i] == 255:  # End option
                break
            elif options_data[i] == 0:  # Pad option
                i += 1
                continue
            
            option_type = options_data[i]
            if i + 1 >= len(options_data):
                break
            
            option_length = options_data[i + 1]
            if i + 2 + option_length > len(options_data):
                break
            
            option_data = options_data[i + 2:i + 2 + option_length]
            
            # Parse specific options
            if option_type == 53:  # DHCP Message Type
                options['message_type'] = option_data[0]
            elif option_type == 50:  # Requested IP Address
                options['requested_ip'] = socket.inet_ntoa(option_data)
            elif option_type == 12:  # Hostname
                options['hostname'] = option_data.decode('utf-8', errors='ignore')
            elif option_type == 55:  # Parameter Request List
                options['parameter_list'] = list(option_data)
            
            i += 2 + option_length
        
        return options
    
    def _handle_discover(self, packet, addr):
        """Handle DHCP DISCOVER message"""
        client_mac = packet['chaddr']
        
        # Find or assign IP address
        offered_ip = self._get_ip_for_client(client_mac)
        if not offered_ip:
            logging.warning(f"No available IP for client {client_mac}")
            return
        
        # Create DHCP OFFER
        offer_packet = self._create_dhcp_packet(
            packet['xid'], 
            offered_ip, 
            client_mac, 
            self.DHCP_OFFER
        )
        
        # Send OFFER
        self._send_dhcp_packet(offer_packet, addr)
        logging.info(f"DHCP OFFER sent to {client_mac}: {offered_ip}")
    
    def _handle_request(self, packet, addr):
        """Handle DHCP REQUEST message"""
        client_mac = packet['chaddr']
        requested_ip = packet.get('requested_ip')
        
        # Validate request
        if self._validate_request(client_mac, requested_ip):
            # Create DHCP ACK
            ack_packet = self._create_dhcp_packet(
                packet['xid'], 
                requested_ip, 
                client_mac, 
                self.DHCP_ACK
            )
            
            # Update lease
            self._update_lease(client_mac, requested_ip)
            
            # Send ACK
            self._send_dhcp_packet(ack_packet, addr)
            logging.info(f"DHCP ACK sent to {client_mac}: {requested_ip}")
        else:
            # Create DHCP NAK
            nak_packet = self._create_dhcp_packet(
                packet['xid'], 
                "0.0.0.0", 
                client_mac, 
                self.DHCP_NAK
            )
            
            # Send NAK
            self._send_dhcp_packet(nak_packet, addr)
            logging.warning(f"DHCP NAK sent to {client_mac}")
    
    def _handle_release(self, packet, addr):
        """Handle DHCP RELEASE message"""
        client_mac = packet['chaddr']
        released_ip = packet['ciaddr']
        
        if client_mac in self.leases:
            del self.leases[client_mac]
        
        if released_ip in self.ip_assignments:
            del self.ip_assignments[released_ip]
            if released_ip not in self.available_ips:
                self.available_ips.append(released_ip)
        
        logging.info(f"DHCP RELEASE from {client_mac}: {released_ip}")
    
    def _handle_decline(self, packet, addr):
        """Handle DHCP DECLINE message"""
        client_mac = packet['chaddr']
        declined_ip = packet.get('requested_ip')
        
        # Mark IP as problematic and remove from pool temporarily
        if declined_ip in self.available_ips:
            self.available_ips.remove(declined_ip)
        
        logging.warning(f"DHCP DECLINE from {client_mac}: {declined_ip}")
    
    def _get_ip_for_client(self, client_mac):
        """Get IP address for client"""
        # Check existing lease
        if client_mac in self.leases:
            lease = self.leases[client_mac]
            if lease['expires'] > datetime.now():
                return lease['ip']
            else:
                # Lease expired
                self._release_lease(client_mac)
        
        # Assign new IP
        if self.available_ips:
            ip = self.available_ips.pop(0)
            return ip
        
        return None
    
    def _validate_request(self, client_mac, requested_ip):
        """Validate DHCP REQUEST"""
        if not requested_ip:
            return False
        
        # Check if IP is in our pool
        if requested_ip not in [f"192.168.4.{i}" for i in range(10, 101)]:
            return False
        
        # Check if IP is available or already assigned to this client
        if requested_ip in self.ip_assignments:
            return self.ip_assignments[requested_ip] == client_mac
        
        return True
    
    def _update_lease(self, client_mac, ip_address):
        """Update DHCP lease"""
        expires = datetime.now() + timedelta(seconds=self.lease_time)
        
        self.leases[client_mac] = {
            'ip': ip_address,
            'expires': expires,
            'hostname': '',
            'assigned_at': datetime.now()
        }
        
        self.ip_assignments[ip_address] = client_mac
    
    def _release_lease(self, client_mac):
        """Release DHCP lease"""
        if client_mac in self.leases:
            lease = self.leases[client_mac]
            ip = lease['ip']
            
            del self.leases[client_mac]
            
            if ip in self.ip_assignments:
                del self.ip_assignments[ip]
            
            if ip not in self.available_ips:
                self.available_ips.append(ip)
    
    def _create_dhcp_packet(self, xid, yiaddr, client_mac, message_type):
        """Create DHCP response packet"""
        packet = bytearray(240)
        
        # DHCP header
        packet[0