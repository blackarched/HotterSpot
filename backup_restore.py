#!/usr/bin/env python3
"""
Backup and Restore Manager
Handles configuration backup, restoration, and migration
"""

import os
import json
import shutil
import tarfile
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import hashlib

class BackupRestoreManager:
    def __init__(self, config_dir: str = "/etc/hotspot", backup_dir: str = "/var/backups/hotspot"):
        self.logger = logging.getLogger(__name__)
        self.config_dir = Path(config_dir)
        self.backup_dir = Path(backup_dir)
        
        # Create directories if they don't exist
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration files to backup
        self.config_files = [
            'hotspot.conf',
            'dhcp.conf',
            'dns.conf',
            'firewall.conf',
            'users.conf',
            'captive_portal.conf'
        ]
        
        # System files to backup (with original paths)
        self.system_files = {
            '/etc/hostapd/hostapd.conf': 'hostapd.conf',
            '/etc/dnsmasq.conf': 'dnsmasq.conf',
            '/etc/iptables/rules.v4': 'iptables_rules.v4',
            '/etc/iptables/rules.v6': 'iptables_rules.v6'
        }
        
        self.max_backups = 10  # Keep only the 10 most recent backups
    
    def create_backup(self, name: Optional[str] = None, description: str = "") -> Tuple[bool, str]:
        """Create a complete backup of hotspot configuration"""
        try:
            # Generate backup name if not provided
            if not name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"hotspot_backup_{timestamp}"
            
            backup_path = self.backup_dir / f"{name}.tar.gz"
            
            # Create temporary directory for backup staging
            temp_dir = self.backup_dir / f"temp_{name}"
            temp_dir.mkdir(exist_ok=True)
            
            try:
                # Backup configuration files
                config_backup_dir = temp_dir / "config"
                config_backup_dir.mkdir(exist_ok=True)
                
                for config_file in self.config_files:
                    source_path = self.config_dir / config_file
                    if source_path.exists():
                        shutil.copy2(source_path, config_backup_dir / config_file)
                        self.logger.debug(f"Backed up config file: {config_file}")
                
                # Backup system files
                system_backup_dir = temp_dir / "system"
                system_backup_dir.mkdir(exist_ok=True)
                
                for system_path, backup_name in self.system_files.items():
                    source_path = Path(system_path)
                    if source_path.exists():
                        shutil.copy2(source_path, system_backup_dir / backup_name)
                        self.logger.debug(f"Backed up system file: {system_path}")
                
                # Create backup metadata
                metadata = {
                    'name': name,
                    'description': description,
                    'created_date': datetime.now().isoformat(),
                    'version': '1.0',
                    'config_files': [f for f in self.config_files if (self.config_dir / f).exists()],
                    'system_files': {k: v for k, v in self.system_files.items() if Path(k).exists()},
                    'checksum': None  # Will be calculated after archive creation
                }
                
                # Write metadata
                with open(temp_dir / "metadata.json", 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                # Create compressed archive
                with tarfile.open(backup_path, 'w:gz') as tar:
                    tar.add(temp_dir, arcname=name)
                
                # Calculate checksum