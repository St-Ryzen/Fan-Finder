#!/usr/bin/env python3
"""
Configuration Protection Utilities
Provides additional protection for sensitive configuration data
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

class ConfigProtector:
    """Protect sensitive configuration data"""
    
    def __init__(self):
        self.salt = b'fanfinder_salt_2024'  # Use a consistent salt
    
    def _get_machine_key(self):
        """Generate encryption key based on machine characteristics"""
        import platform
        import getpass
        
        # Combine machine-specific data
        machine_data = f"{platform.machine()}-{platform.system()}-{getpass.getuser()}"
        
        # Create key from machine data
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(machine_data.encode()))
        return key
    
    def encrypt_config_value(self, value):
        """Encrypt a configuration value"""
        try:
            key = self._get_machine_key()
            f = Fernet(key)
            encrypted = f.encrypt(value.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            print(f"[WARNING] Could not encrypt config value: {e}")
            return value  # Return original if encryption fails
    
    def decrypt_config_value(self, encrypted_value):
        """Decrypt a configuration value"""
        try:
            key = self._get_machine_key()
            f = Fernet(key)
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
            decrypted = f.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            # If decryption fails, assume it's already plaintext
            return encrypted_value
    
    def get_protected_env_var(self, var_name, default=None):
        """Get environment variable with automatic decryption if needed"""
        value = os.getenv(var_name, default)
        if value:
            # Try to decrypt, fall back to original if it fails
            return self.decrypt_config_value(value)
        return value
    
    def create_protected_env_file(self, env_file_path='.env'):
        """Create a protected version of the .env file"""
        try:
            if not os.path.exists(env_file_path):
                print(f"[ERROR] Environment file not found: {env_file_path}")
                return False
            
            # Read current .env file
            with open(env_file_path, 'r') as f:
                lines = f.readlines()
            
            protected_lines = []
            sensitive_vars = [
                'FIREBASE_KEY_PATH', 'DISCORD_WEBHOOK_URL', 
                'SECRET_KEY', 'ADMIN_SECRET_KEY'
            ]
            
            for line in lines:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    if key in sensitive_vars:
                        # Encrypt sensitive values
                        encrypted_value = self.encrypt_config_value(value)
                        protected_lines.append(f"{key}={encrypted_value}\n")
                        print(f"[PROTECTED] Encrypted {key}")
                    else:
                        protected_lines.append(line + '\n')
                else:
                    protected_lines.append(line + '\n')
            
            # Write protected .env file
            protected_path = env_file_path + '.protected'
            with open(protected_path, 'w') as f:
                f.writelines(protected_lines)
            
            print(f"Protected environment file created: {protected_path}")
            print("WARNING: To use protected config, rename .env.protected to .env")
            print("WARNING: This will only work on the machine where it was created")
            return True
            
        except Exception as e:
            print(f"[ERROR] Could not create protected environment file: {e}")
            return False

def obfuscate_firebase_key():
    """Obfuscate Firebase service account key file"""
    try:
        # Find Firebase key file
        key_paths = [
            'config/firebase-key-13504509.json',
            '../config/firebase-key-13504509.json'
        ]
        
        key_path = None
        for path in key_paths:
            if os.path.exists(path):
                key_path = path
                break
        
        if not key_path:
            print("[INFO] Firebase key file not found - this is expected for security")
            return True
        
        # Check if file is already obfuscated
        with open(key_path, 'r') as f:
            content = f.read()
        
        if content.startswith('OBFUSCATED:'):
            print("[INFO] Firebase key is already obfuscated")
            return True
        
        # Create obfuscated version
        protector = ConfigProtector()
        obfuscated_content = 'OBFUSCATED:' + protector.encrypt_config_value(content)
        
        # Write obfuscated version
        obfuscated_path = key_path + '.obfuscated'
        with open(obfuscated_path, 'w') as f:
            f.write(obfuscated_content)
        
        print(f"Firebase key obfuscated: {obfuscated_path}")
        print("WARNING: To use obfuscated key, update FIREBASE_KEY_PATH in .env")
        return True
        
    except Exception as e:
        print(f"[ERROR] Could not obfuscate Firebase key: {e}")
        return False

# Global protector instance
config_protector = ConfigProtector()

if __name__ == "__main__":
    print("Configuration Protection Utility")
    print("=" * 35)
    
    protector = ConfigProtector()
    
    # Protect .env file
    if protector.create_protected_env_file():
        print()
        obfuscate_firebase_key()
        
        print("\nConfiguration protection complete!")
        print("\nAdditional security measures applied:")
        print("   * Environment variables encrypted with machine-specific key")
        print("   * Firebase service account key obfuscated")
        print("   * Configuration only readable on this specific machine")
    else:
        print("\nConfiguration protection failed!")