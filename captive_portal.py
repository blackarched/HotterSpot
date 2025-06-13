#!/usr/bin/env python3
"""
Captive Portal Module for Hotspot Tool
Provides web interface for user authentication and terms acceptance
"""

import os
import sys
import json
import time
import threading
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, session, jsonify
from werkzeug.serving import make_server
import logging

class CaptivePortal:
    def __init__(self, config_manager, user_manager):
        self.config_manager = config_manager
        self.user_manager = user_manager
        self.app = Flask(__name__)
        self.app.secret_key = os.urandom(24)
        self.server = None
        self.server_thread = None
        self.running = False
        
        # Setup database
        self.db_path = "captive_portal.db"
        self.init_database()
        
        # Setup routes
        self.setup_routes()
        
        # Configure logging
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    def init_database(self):
        """Initialize the captive portal database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portal_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mac_address TEXT UNIQUE,
                ip_address TEXT,
                authenticated BOOLEAN DEFAULT FALSE,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_agent TEXT,
                accepted_terms BOOLEAN DEFAULT FALSE
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def setup_routes(self):
        """Setup Flask routes for the captive portal"""
        
        @self.app.route('/')
        def index():
            client_ip = request.environ.get('REMOTE_ADDR')
            mac_address = self.get_mac_from_ip(client_ip)
            
            if self.is_authenticated(mac_address):
                return redirect('/success')
            
            return render_template_string(self.get_portal_template(), 
                                        hotspot_name=self.config_manager.get_config().get('hotspot_name', 'WiFi Hotspot'))
        
        @self.app.route('/authenticate', methods=['POST'])
        def authenticate():
            client_ip = request.environ.get('REMOTE_ADDR')
            mac_address = self.get_mac_from_ip(client_ip)
            user_agent = request.headers.get('User-Agent', '')
            
            # Check if terms were accepted
            terms_accepted = request.form.get('accept_terms') == 'on'
            
            if not terms_accepted:
                return render_template_string(self.get_portal_template(error="You must accept the terms of service"), 
                                            hotspot_name=self.config_manager.get_config().get('hotspot_name', 'WiFi Hotspot'))
            
            # Authenticate user
            self.authenticate_device(mac_address, client_ip, user_agent)
            
            return redirect('/success')
        
        @self.app.route('/success')
        def success():
            return render_template_string(self.get_success_template())
        
        @self.app.route('/status')
        def status():
            client_ip = request.environ.get('REMOTE_ADDR')
            mac_address = self.get_mac_from_ip(client_ip)
            
            return jsonify({
                'authenticated': self.is_authenticated(mac_address),
                'ip': client_ip,
                'mac': mac_address
            })
    
    def get_mac_from_ip(self, ip_address):
        """Get MAC address from IP address using ARP table"""
        try:
            import subprocess
            result = subprocess.run(['arp', '-n', ip_address], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if ip_address in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            return parts[2]  # MAC address
        except Exception as e:
            logging.error(f"Error getting MAC address for {ip_address}: {e}")
        
        return f"unknown_{ip_address.replace('.', '_')}"
    
    def is_authenticated(self, mac_address):
        """Check if device is authenticated"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT authenticated FROM portal_sessions 
            WHERE mac_address = ? AND authenticated = TRUE
        ''', (mac_address,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    def authenticate_device(self, mac_address, ip_address, user_agent):
        """Authenticate a device"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO portal_sessions 
            (mac_address, ip_address, authenticated, user_agent, accepted_terms, timestamp)
            VALUES (?, ?, TRUE, ?, TRUE, CURRENT_TIMESTAMP)
        ''', (mac_address, ip_address, user_agent))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Device authenticated: {mac_address} ({ip_address})")
    
    def get_portal_template(self, error=None):
        """Get the captive portal HTML template"""
        return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ hotspot_name }} - Welcome</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            max-width: 400px;
            width: 90%;
            text-align: center;
        }
        .logo {
            font-size: 2rem;
            color: #667eea;
            margin-bottom: 1rem;
        }
        .error {
            color: #dc3545;
            margin-bottom: 1rem;
            padding: 0.5rem;
            background: #f8d7da;
            border-radius: 5px;
        }
        .terms {
            text-align: left;
            margin: 1rem 0;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 5px;
            max-height: 200px;
            overflow-y: auto;
        }
        .checkbox-container {
            margin: 1rem 0;
            text-align: left;
        }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1rem;
            width: 100%;
        }
        .btn:hover {
            background: #5a67d8;
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">📶 {{ hotspot_name }}</div>
        <h2>Welcome to our WiFi Network</h2>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="POST" action="/authenticate">
            <div class="terms">
                <h4>Terms of Service</h4>
                <p>By using this WiFi network, you agree to:</p>
                <ul>
                    <li>Use the network responsibly and legally</li>
                    <li>Not engage in any illegal activities</li>
                    <li>Not attempt to access restricted resources</li>
                    <li>Respect bandwidth limits and fair usage</li>
                    <li>Allow monitoring of network usage for security purposes</li>
                </ul>
                <p>Your connection may be monitored and logged for security and performance purposes.</p>
            </div>
            
            <div class="checkbox-container">
                <label>
                    <input type="checkbox" name="accept_terms" required> 
                    I accept the terms of service
                </label>
            </div>
            
            <button type="submit" class="btn">Connect to Internet</button>
        </form>
    </div>
</body>
</html>
        '''
    
    def get_success_template(self):
        """Get the success page HTML template"""
        return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connected Successfully</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 2rem;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            max-width: 400px;
            width: 90%;
            text-align: center;
        }
        .success-icon {
            font-size: 4rem;
            color: #28a745;
            margin-bottom: 1rem;
        }
        .btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 0.75rem 2rem;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1rem;
            text-decoration: none;
            display: inline-block;
            margin-top: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h2>Successfully Connected!</h2>
        <p>You now have access to the internet. Enjoy your browsing!</p>
        <a href="http://www.google.com" class="btn">Start Browsing</a>
    </div>
    
    <script>
        // Auto-redirect after 5 seconds
        setTimeout(function() {
            window.location.href = 'http://www.google.com';
        }, 5000);
    </script>
</body>
</html>
        '''
    
    def start_portal(self, host='0.0.0.0', port=8080):
        """Start the captive portal web server"""
        if self.running:
            return False
        
        try:
            self.server = make_server(host, port, self.app, threaded=True)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            self.running = True
            
            logging.info(f"Captive portal started on {host}:{port}")
            return True
        except Exception as e:
            logging.error(f"Failed to start captive portal: {e}")
            return False
    
    def stop_portal(self):
        """Stop the captive portal web server"""
        if not self.running:
            return False
        
        try:
            if self.server:
                self.server.shutdown()
                self.server_thread.join(timeout=5)
            
            self.running = False
            logging.info("Captive portal stopped")
            return True
        except Exception as e:
            logging.error(f"Failed to stop captive portal: {e}")
            return False
    
    def get_authenticated_devices(self):
        """Get list of authenticated devices"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT mac_address, ip_address, timestamp, user_agent 
            FROM portal_sessions 
            WHERE authenticated = TRUE
            ORDER BY timestamp DESC
        ''')
        
        devices = []
        for row in cursor.fetchall():
            devices.append({
                'mac_address': row[0],
                'ip_address': row[1],
                'timestamp': row[2],
                'user_agent': row[3]
            })
        
        conn.close()
        return devices
    
    def revoke_access(self, mac_address):
        """Revoke access for a device"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE portal_sessions 
            SET authenticated = FALSE 
            WHERE mac_address = ?
        ''', (mac_address,))
        
        conn.commit()
        conn.close()
        
        logging.info(f"Access revoked for device: {mac_address}")
    
    def clear_all_sessions(self):
        """Clear all portal sessions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM portal_sessions')
        
        conn.commit()
        conn.close()
        
        logging.info("All portal sessions cleared")
    
    def get_status(self):
        """Get captive portal status"""
        return {
            'running': self.running,
            'authenticated_devices': len(self.get_authenticated_devices())
        }

if __name__ == "__main__":
    # Test the captive portal
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from config_manager import ConfigManager
    from user_manager import UserManager
    
    config_manager = ConfigManager()
    user_manager = UserManager(config_manager)
    
    portal = CaptivePortal(config_manager, user_manager)
    
    if portal.start_portal():
        print("Captive portal started on http://localhost:8080")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            portal.stop_portal()
            print("\nCaptive portal stopped")
    else:
        print("Failed to start captive portal")
