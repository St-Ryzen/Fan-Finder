#!/usr/bin/env python3
"""
Credential Manager for Model Account Management
Handles encryption/decryption of model credentials stored in Supabase
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CredentialManager:
    """Manages encryption and decryption of model credentials"""

    def __init__(self):
        """Initialize credential manager with encryption key from environment"""
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)

    def _get_or_create_encryption_key(self):
        """Get encryption key from environment or generate one"""
        env_key = os.getenv('MODEL_ENCRYPTION_KEY')

        if env_key:
            try:
                # Verify the key is valid
                Fernet(env_key.encode() if isinstance(env_key, str) else env_key)
                return env_key.encode() if isinstance(env_key, str) else env_key
            except Exception as e:
                print(f"[ERROR] Invalid MODEL_ENCRYPTION_KEY in environment: {e}")
                raise ValueError("Invalid encryption key in MODEL_ENCRYPTION_KEY environment variable")

        # If no key in environment, generate one (for development/setup)
        print("[WARNING] MODEL_ENCRYPTION_KEY not found in environment")
        print("[WARNING] Generating a new encryption key for development")
        print("[WARNING] For production, set MODEL_ENCRYPTION_KEY environment variable")

        new_key = Fernet.generate_key()
        print(f"[INFO] Generated encryption key: {new_key.decode()}")
        print("[INFO] Set this as MODEL_ENCRYPTION_KEY in your .env file")

        return new_key

    def encrypt_credentials(self, username: str, password: str) -> dict:
        """
        Encrypt username and password

        Args:
            username: Model account username
            password: Model account password

        Returns:
            Dictionary with encrypted_username and encrypted_password
        """
        try:
            encrypted_username = self.cipher.encrypt(username.encode()).decode()
            encrypted_password = self.cipher.encrypt(password.encode()).decode()

            return {
                'username': encrypted_username,
                'password': encrypted_password
            }
        except Exception as e:
            print(f"[ERROR] Failed to encrypt credentials: {e}")
            raise

    def decrypt_credentials(self, encrypted_username: str, encrypted_password: str) -> dict:
        """
        Decrypt username and password

        Args:
            encrypted_username: Encrypted username from Supabase
            encrypted_password: Encrypted password from Supabase

        Returns:
            Dictionary with decrypted username and password
        """
        try:
            username = self.cipher.decrypt(encrypted_username.encode()).decode()
            password = self.cipher.decrypt(encrypted_password.encode()).decode()

            return {
                'username': username,
                'password': password
            }
        except Exception as e:
            print(f"[ERROR] Failed to decrypt credentials: {e}")
            raise

    def encrypt_password_only(self, password: str) -> str:
        """Encrypt a single password"""
        try:
            return self.cipher.encrypt(password.encode()).decode()
        except Exception as e:
            print(f"[ERROR] Failed to encrypt password: {e}")
            raise

    def decrypt_password_only(self, encrypted_password: str) -> str:
        """Decrypt a single password"""
        try:
            return self.cipher.decrypt(encrypted_password.encode()).decode()
        except Exception as e:
            print(f"[ERROR] Failed to decrypt password: {e}")
            raise


# Global credential manager instance
credential_manager = CredentialManager()


def generate_encryption_key():
    """
    Utility function to generate a new encryption key
    Run this to create a key for the first time
    """
    key = Fernet.generate_key()
    print("=" * 50)
    print("NEW ENCRYPTION KEY GENERATED")
    print("=" * 50)
    print("\nAdd this to your .env file:")
    print(f"MODEL_ENCRYPTION_KEY={key.decode()}")
    print("\n" + "=" * 50)
    return key


if __name__ == "__main__":
    # Generate a new encryption key if running this module directly
    generate_encryption_key()
