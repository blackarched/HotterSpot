#!/usr/bin/env python3
"""
GUI Dashboard - Main graphical user interface for the hotspot tool
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import logging
from typing import Dict, List
import json
from datetime import datetime

# Import our custom modules
from hotspot_manager import HotspotManager
from bandwidth_manager import BandwidthManager
from user_manager import UserManager
from config_manager import ConfigManager
from network_monitor import NetworkMonitor
from status_logger import StatusLogger

class HotspotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Hotspot Control Panel")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)
        
        # Initialize managers
        self.hotspot_manager = HotspotManager()
        self.bandwidth_manager = BandwidthManager()
        self.user_manager = UserManager()
        self.config_manager = ConfigManager()
        self.network_monitor = NetworkMonitor()
        self.status_logger = StatusLogger()
        
        # GUI state
        self.hotspot_active = False
        self.connected_devices = []
        self.monitoring_active = False
        
        # Create GUI elements
        self.create_widgets()
        self.load_settings()
        
        # Start monitoring thread
        self.start_monitoring()
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        """Create all GUI widgets"""
        # Create main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_main_tab()
        self.create_devices_tab()
        self.create_settings_tab()
        self.create_monitoring_tab()
        self.create_logs_tab()
    
    def create_main_tab(self):
        """Create main control tab"""
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text="Main Control")
        
        # Hotspot control section
        control_frame = ttk.LabelFrame(main_frame, text="Hotspot Control", padding=10)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        # Status display
        self.status_var = tk.StringVar(value="Hotspot: Inactive")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, font=('Arial', 12, 'bold'))
        status_label.pack(pady=5)
        
        # SSID and Password
        settings_frame = ttk.Frame(control_frame)
        settings_frame.pack(fill='x', pady=10)
        
        ttk.Label(settings_frame, text="Network Name (SSID):").grid(row=0, column=0, sticky='w', padx=5)
        self.ssid_var = tk.StringVar(value="MyHotspot")
        self.ssid_entry = ttk.Entry(settings_frame, textvariable=self.ssid_var, width=20)
        self.ssid_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(settings_frame, text="Password:").grid(row=1, column=0, sticky='w', padx=5)
        self.password_var = tk.StringVar(value="12345678")
        self.password_entry = ttk.Entry(settings_frame, textvariable=self.password_var, show='*', width=20)
        self.password_entry.grid(row=1, column=1, padx=5)
        
        self.show_password_var = tk.BooleanVar()
        show_pass_cb = ttk.Checkbutton(settings_frame, text="Show Password", 
                                      variable=self.show_password_var, command=self.toggle_password)
        show_pass_cb.grid(row=1, column=2, padx=5)
        
        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start Hotspot", 
                                      command=self.start_hotspot, style='Accent.TButton')
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop Hotspot", 
                                     command=self.stop_hotspot, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        # Status information
        info_frame = ttk.LabelFrame(main_frame, text="Status Information", padding=10)
        info_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create treeview for status info
        self.status_tree = ttk.Treeview(info_frame, columns=('Value',), show='tree headings', height=6)
        self.status_tree.heading('#0', text='Property')
        self.status_tree.heading('Value', text='Value')
        self.status_tree.column('#0', width=200)
        self.status_tree.column('Value', width=300)
        
        scrollbar = ttk.Scrollbar(info_frame, orient='vertical', command=self.status_tree.yview)
        self.status_tree.configure(yscrollcommand=scrollbar.set)
        
        self.status_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
    
    def create_devices_tab(self):
        """Create connected devices tab"""
        devices_frame = ttk.Frame(self.notebook)
        self.notebook.add(devices_frame, text="Connected Devices")
        
        # Devices list
        list_frame = ttk.LabelFrame(devices_frame, text="Connected Devices", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create treeview for devices
        columns = ('Hostname', 'IP Address', 'MAC Address', 'Data Usage', 'Status')
        self.devices_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.devices_tree.heading(col, text=col)
            self.devices_tree.column(col, width=150)
        
        device_scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.devices_tree.yview)
        self.devices_tree.configure(yscrollcommand=device_scrollbar.set)
        
        self.devices_tree.pack(side='left', fill='both', expand=True)
        device_scrollbar.pack(side='right', fill='y')
        
        # Device control buttons
        control_frame = ttk.Frame(devices_frame)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(control_frame, text="Refresh", command=self.refresh_devices).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Block Device", command=self.block_selected_device).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Unblock Device", command=self.unblock_selected_device).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Set Friendly Name", command=self.set_device_name).pack(side='left', padx=5)
    
    def create_settings_tab(self):
        """Create settings tab"""
        settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")
        
        # Network settings
        network_frame = ttk.LabelFrame(settings_frame, text="Network Settings", padding=10)
        network_frame.pack(fill='x', padx=10, pady=10)
        
        # Interface selection
        ttk.Label(network_frame, text="Wireless Interface:").grid(row=0, column=0, sticky='w', padx=5)
        self.interface_var = tk.StringVar()
        self.interface_combo = ttk.Combobox(network_frame, textvariable=self.interface_var, state='readonly')
        self.interface_combo.grid(row=0, column=1, padx=5, sticky='ew')
        
        # Refresh interfaces button
        ttk.Button(network_frame, text="Refresh", command=self.refresh_interfaces).grid(row=0, column=2, padx=5)
        
        # Security settings
        ttk.Label(network_frame, text="Security Type:").grid(row=1, column=0, sticky='w', padx=5)
        self.security_var = tk.StringVar(value="WPA2")
        security_combo = ttk.Combobox(network_frame, textvariable=self.security_var, 
                                     values=["WPA2", "WPA3"], state='readonly')
        security_combo.grid(row=1, column=1, padx=5, sticky='ew')
        
        network_frame.columnconfigure(1, weight=1)
        
        # Bandwidth settings
        bandwidth_frame = ttk.LabelFrame(settings_frame, text="Bandwidth Control", padding=10)
        bandwidth_frame.pack(fill='x', padx=10, pady=10)
        
        self.limit_bandwidth_var = tk.BooleanVar()
        limit_cb = ttk.Checkbutton(bandwidth_frame, text="Enable Bandwidth Limiting", 
                                  variable=self.limit_bandwidth_var, command=self.toggle_bandwidth_controls)
        limit_cb.pack(anchor='w')
        
        limits_frame = ttk.Frame(bandwidth_frame)
        limits_frame.pack(fill='x', pady=5)
        
        ttk.Label(limits_frame, text="Download Limit (Mbps):").grid(row=0, column=0, sticky='w', padx=5)
        self.download_limit_var = tk.StringVar(value="10")
        self.download_entry = ttk.Entry(limits_frame, textvariable=self.download_limit_var, width=10, state='disabled')
        self.download_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(limits_frame, text="Upload Limit (Mbps):").grid(row=1, column=0, sticky='w', padx=5)
        self.upload_limit_var = tk.StringVar(value="5")
        self.upload_entry = ttk.Entry(limits_frame, textvariable=self.upload_limit_var, width=10, state='disabled')
        self.upload_entry.grid(row=1, column=1, padx=5)
        
        # Apply settings button
        ttk.Button(settings_frame, text="Apply Settings", command=self.apply_settings).pack(pady=10)
    
    def create_monitoring_tab(self):
        """Create monitoring tab"""
        monitoring_frame = ttk.Frame(self.notebook)
        self.notebook.add(monitoring_frame, text="Monitoring")
        
        # Real-time stats
        stats_frame = ttk.LabelFrame(monitoring_frame, text="Real-time Statistics", padding=10)
        stats_frame.pack(fill='x', padx=10, pady=10)
        
        # Stats display
        self.stats_text = tk.Text(stats_frame, height=10, width=80)
        stats_scroll = ttk.Scrollbar(stats_frame, orient='vertical', command=self.stats_text.yview)
        self.stats_text.configure(yscrollcommand=stats_scroll.set)
        
        self.stats_text.pack(side='left', fill='both', expand=True)
        stats_scroll.pack(side='right', fill='y')
        
        # Control buttons
        control_frame = ttk.Frame(monitoring_frame)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        self.monitor_button = ttk.Button(control_frame, text="Start Monitoring", command=self.toggle_monitoring)
        self.monitor_button.pack(side='left', padx=5)
        
        ttk.Button(control_frame, text="Clear Stats", command=self.clear_stats).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Export Stats", command=self.export_stats).pack(side='left', padx=5)
    
    def create_logs_tab(self):
        """Create logs tab"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="Logs")
        
        # Log display
        log_frame = ttk.LabelFrame(logs_frame, text="System Logs", padding=10)
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.log_text = tk.Text(log_frame, height=20, width=100)
        log_scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scroll.pack(side='right', fill='y')
        
        # Log controls
        log_control_frame = ttk.Frame(logs_frame)
        log_control_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(log_control_frame, text="Refresh Logs", command=self.refresh_logs).pack(side='left', padx=5)
        ttk.Button(log_control_frame, text="Clear Logs", command=self.clear_logs).pack(side='left', padx=5)
        ttk.Button(log_control_frame, text="Export Logs", command=self.export_logs).pack(side='left', padx=5)
    
    def toggle_password(self):
        """Toggle password visibility"""
        if self.show_password_var.get():
            self.password_entry.configure(show='')
        else:
            self.password_entry.configure(show='*')
    
    def start_hotspot(self):
        """Start the hotspot"""
        ssid = self.ssid_var.get().strip()
        password = self.password_var.get().strip()
        
        if not ssid:
            messagebox.showerror("Error", "Please enter a network name (SSID)")
            return
        
        if len(password) < 8:
            messagebox.showerror("Error", "Password must be at least 8 characters long")
            return
        
        # Start hotspot in separate thread to avoid blocking GUI
        threading.Thread(target=self._start_hotspot_thread, args=(ssid, password), daemon=True).start()
    
    def _start_hotspot_thread(self, ssid, password):
        """Start hotspot in background thread"""
        try:
            interface = self.interface_var.get() or None
            success = self.hotspot_manager.create_hotspot(ssid, password, interface)
            
            if success:
                self.root.after(0, self._hotspot_started)
                
                # Apply bandwidth limits if enabled
                if self.limit_bandwidth_var.get():
                    download_limit = float(self.download_limit_var.get())
                    upload_limit = float(self.upload_limit_var.get())
                    self.bandwidth_manager.set_bandwidth_limit(
                        self.hotspot_manager.interface, download_limit, upload_limit
                    )
            else:
                self.root.after(0, lambda: messagebox.showerror("Error", "Failed to start hotspot"))
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Error starting hotspot: {e}"))
    
    def _hotspot_started(self):
        """Update GUI after hotspot starts"""
        self.hotspot_active = True
        self.status_var.set("Hotspot: Active")
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.user_manager.start_monitoring()
    
    def stop_hotspot(self):
        """Stop the hotspot"""
        threading.Thread(target=self._stop_hotspot_thread, daemon=True).start()
    
    def _stop_hotspot_thread(self):
        """Stop hotspot in background thread"""
        try:
            success = self.hotspot_manager.stop_hotspot()
            self.root.after(0, self._hotspot_stopped)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Error stopping hotspot: {e}"))
    
    def _hotspot_stopped(self):
        """Update GUI after hotspot stops"""
        self.hotspot_active = False
        self.status_var.set("Hotspot: Inactive")
        self.start_button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        self.user_manager.stop_monitoring()
        
        # Clear devices list
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)
    
    def refresh_interfaces(self):
        """Refresh available network interfaces"""
        interfaces = self.hotspot_manager.get_available_interfaces()
        self.interface_combo['values'] = interfaces
        if interfaces:
            self.interface_combo.set(interfaces[0])
    
    def toggle_bandwidth_controls(self):
        """Toggle bandwidth control elements"""
        state = 'normal' if self.limit_bandwidth_var.get() else 'disabled'
        self.download_entry.configure(state=state)
        self.upload_entry.configure(state=state)
    
    def refresh_devices(self):
        """Refresh connected devices list"""
        if not self.hotspot_active:
            return
            
        # Clear current items
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)
        
        # Get connected devices
        devices = self.hotspot_manager.get_connected_devices()
        
        for device in devices:
            hostname = device.get('hostname', 'Unknown')
            ip = device.get('ip', 'Unknown')
            mac = device.get('mac', 'Unknown')
            
            # Get data usage
            usage_data = self.user_manager.get_device_usage(mac, 24)
            total_bytes = usage_data.get('total_bytes', 0)
            usage_str = f"{total_bytes / (1024*1024):.1f} MB" if total_bytes > 0 else "0 MB"
            
            # Check if blocked
            blocked_devices = self.user_manager.get_blocked_devices()
            is_blocked = any(bd['mac'] == mac for bd in blocked_devices)
            status = "Blocked" if is_blocked else "Connected"
            
            self.devices_tree.insert('', 'end', values=(hostname, ip, mac, usage_str, status))
    
    def block_selected_device(self):
        """Block selected device"""
        selection = self.devices_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a device to block")
            return
        
        item = self.devices_tree.item(selection[0])
        mac_address = item['values'][2]
        
        reason = simpledialog.askstring("Block Device", "Enter reason for blocking (optional):")
        if reason is None:  # User cancelled
            return
        
        success = self.user_manager.block_device(mac_address, reason or "Manual block")
        if success:
            messagebox.showinfo("Success", "Device blocked successfully")
            self.refresh_devices()
        else:
            messagebox.showerror("Error", "Failed to block device")
    
    def unblock_selected_device(self):
        """Unblock selected device"""
        selection = self.devices_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a device to unblock")
            return
        
        item = self.devices_tree.item(selection[0])
        mac_address = item['values'][2]
        
        success = self.user_manager.unblock_device(mac_address)
        if success:
            messagebox.showinfo("Success", "Device unblocked successfully")
            self.refresh_devices()
        else:
            messagebox.showerror("Error", "Failed to unblock device")
    
    def set_device_name(self):
        """Set friendly name for selected device"""
        selection = self.devices_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a device")
            return
        
        item = self.devices_tree.item(selection[0])
        mac_address = item['values'][2]
        current_name = item['values'][0]
        
        new_name = simpledialog.askstring("Set Device Name", 
                                         f"Enter friendly name for device {mac_address}:",
                                         initialvalue=current_name)
        if new_name:
            success = self.user_manager.set_friendly_name(mac_address, new_name)
            if success:
                messagebox.showinfo("Success", "Device name updated")
                self.refresh_devices()
            else:
                messagebox.showerror("Error", "Failed to update device name")
    
    def apply_settings(self):
        """Apply configuration settings"""
        # Save settings to config
        settings = {
            'ssid': self.ssid_var.get(),
            'password': self.password_var.get(),
            'interface': self.interface_var.get(),
            'security': self.security_var.get(),
            'bandwidth_limit_enabled': self.limit_bandwidth_var.get(),
            'download_limit': self.download_limit_var.get(),
            'upload_limit': self.upload_limit_var.get()
        }
        
        self.config_manager.save_config('gui_settings', settings)
        messagebox.showinfo("Success", "Settings saved successfully")
    
    def load_settings(self):
        """Load saved settings"""
        settings = self.config_manager.load_config('gui_settings')
        if settings:
            self.ssid_var.set(settings.get('ssid', 'MyHotspot'))
            self.password_var.set(settings.get('password', '12345678'))
            self.security_var.set(settings.get('security', 'WPA2'))
            self.limit_bandwidth_var.set(settings.get('bandwidth_limit_enabled', False))
            self.download_limit_var.set(settings.get('download_limit', '10'))
            self.upload_limit_var.set(settings.get('upload_limit', '5'))
            
            # Update bandwidth controls state
            self.toggle_bandwidth_controls()
        
        # Refresh interfaces
        self.refresh_interfaces()
    
    def toggle_monitoring(self):
        """Toggle network monitoring"""
        if self.monitoring_active:
            self.monitoring_active = False
            self.monitor_button.configure(text="Start Monitoring")
        else:
            self.monitoring_active = True
            self.monitor_button.configure(text="Stop Monitoring")
            threading.Thread(target=self._monitoring_thread, daemon=True).start()
    
    def _monitoring_thread(self):
        """Background monitoring thread"""
        while self.monitoring_active:
            try:
                if self.hotspot_active and self.hotspot_manager.interface:
                    usage = self.bandwidth_manager.get_bandwidth_usage(self.hotspot_manager.interface, 1.0)
                    if usage:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        stats_text = f"[{timestamp}] Upload: {usage['upload_mbps']:.2f} Mbps, Download: {usage['download_mbps']:.2f} Mbps\n"
                        
                        self.root.after(0, lambda: self._update_stats_display(stats_text))
                
                time.sleep(5)
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                time.sleep(5)
    
    def _update_stats_display(self, text):
        """Update stats display in GUI thread"""
        self.stats_text.insert(tk.END, text)
        self.stats_text.see(tk.END)
        
        # Limit text length
        if len(self.stats_text.get('1.0', tk.END)) > 10000:
            self.stats_text.delete('1.0', '100.0')
    
    def clear_stats(self):
        """Clear statistics display"""
        self.stats_text.delete('1.0', tk.END)
    
    def export_stats(self):
        """Export statistics to file"""
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.stats_text.get('1.0', tk.END))
                messagebox.showinfo("Success", f"Statistics exported to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export statistics: {e}")
    
    def refresh_logs(self):
        """Refresh log display"""
        # Implementation would read from log files
        self.log_text.insert(tk.END, f"[{datetime.now()}] Log refresh requested\n")
    
    def clear_logs(self):
        """Clear log display"""
        self.log_text.delete('1.0', tk.END)
    
    def export_logs(self):
        """Export logs to file"""
        from tkinter import filedialog
        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_text.get('1.0', tk.END