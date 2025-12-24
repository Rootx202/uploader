"""
Security utilities for the Remote File Uploader
"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import keyring
import getpass
from PyQt5.QtCore import QSettings

class PasswordManager:
    """Secure password management using keyring and encryption"""
    
    def __init__(self, app_name="RemoteFileUploader"):
        self.app_name = app_name
        self.settings = QSettings("EnhancedUploader", "Settings")
        
    def _generate_key_from_machine(self):
        """Generate encryption key based on machine characteristics"""
        try:
            # Try to get machine ID or create one
            machine_id = self._get_or_create_machine_id()
            
            # Create key from machine ID
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'uploader_salt_2024',  # Static salt for consistency
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
            return key
        except Exception as e:
            # Fallback: use a default key (less secure but functional)
            return Fernet.generate_key()
    
    def _get_or_create_machine_id(self):
        """Get or create unique machine identifier"""
        machine_id = self.settings.value("machine_id", None)
        if not machine_id:
            # Generate new machine ID
            import uuid
            machine_id = str(uuid.uuid4())
            self.settings.setValue("machine_id", machine_id)
            self.settings.sync()
        return machine_id
    
    def encrypt_password(self, password: str) -> str:
        """Encrypt password using Fernet encryption"""
        if not password:
            return ""
        
        try:
            key = self._generate_key_from_machine()
            f = Fernet(key)
            encrypted = f.encrypt(password.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            # Log error but don't expose password
            print(f"Password encryption failed: {type(e).__name__}")
            return password  # Return original as fallback
    
    def decrypt_password(self, encrypted_password: str) -> str:
        """Decrypt password"""
        if not encrypted_password:
            return ""
        
        try:
            key = self._generate_key_from_machine()
            f = Fernet(key)
            
            # Decode and decrypt
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode())
            decrypted = f.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            # If decryption fails, assume it's already plain text (for backward compatibility)
            return encrypted_password
    
    def save_server_credentials(self, server_name: str, username: str, password: str):
        """Save server credentials securely"""
        try:
            # Try to use system keyring first (most secure)
            keyring.set_password(self.app_name, f"{server_name}_username", username)
            keyring.set_password(self.app_name, f"{server_name}_password", password)
            return True
        except Exception:
            # Fallback to encrypted storage in settings
            encrypted_password = self.encrypt_password(password)
            self.settings.setValue(f"credentials/{server_name}/username", username)
            self.settings.setValue(f"credentials/{server_name}/password", encrypted_password)
            self.settings.sync()
            return True
    
    def get_server_credentials(self, server_name: str) -> tuple:
        """Get server credentials securely"""
        try:
            # Try keyring first
            username = keyring.get_password(self.app_name, f"{server_name}_username")
            password = keyring.get_password(self.app_name, f"{server_name}_password")
            
            if username and password:
                return username, password
        except Exception:
            pass
        
        # Fallback to encrypted settings
        username = self.settings.value(f"credentials/{server_name}/username", "")
        encrypted_password = self.settings.value(f"credentials/{server_name}/password", "")
        
        if username and encrypted_password:
            password = self.decrypt_password(encrypted_password)
            return username, password
        
        return "", ""
    
    def delete_server_credentials(self, server_name: str):
        """Delete server credentials securely"""
        try:
            # Remove from keyring
            keyring.delete_password(self.app_name, f"{server_name}_username")
            keyring.delete_password(self.app_name, f"{server_name}_password")
        except Exception:
            pass
        
        # Remove from settings
        self.settings.remove(f"credentials/{server_name}/username")
        self.settings.remove(f"credentials/{server_name}/password")
        self.settings.sync()

class FileEncryption:
    """File encryption for sensitive uploads"""
    
    @staticmethod
    def encrypt_file(file_path: str, password: str) -> str:
        """Encrypt file with password and return encrypted file path"""
        import pyzipper
        
        encrypted_path = file_path + ".encrypted.zip"
        
        with pyzipper.AESZipFile(encrypted_path, 'w', compression=pyzipper.ZIP_LZMA, 
                                encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(password.encode())
            zf.write(file_path, os.path.basename(file_path))
        
        return encrypted_path
    
    @staticmethod
    def generate_strong_password(length: int = 16) -> str:
        """Generate strong random password"""
        import secrets
        import string
        
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        return password

# Usage example and migration function
def migrate_existing_passwords():
    """Migrate existing plain text passwords to encrypted format"""
    settings = QSettings("EnhancedUploader", "Settings")
    password_manager = PasswordManager()
    
    # Get all saved servers
    servers = settings.value("servers", {})
    if not isinstance(servers, dict):
        return
    
    migrated_count = 0
    for server_name, server_data in servers.items():
        if 'config' in server_data:
            config = server_data['config']
            
            # Check if password field exists and is not encrypted yet
            password = config.get('password', '')
            username = config.get('username', '')
            
            if password and username and len(password) < 100:  # Assume short passwords are not encrypted
                # Migrate to secure storage
                password_manager.save_server_credentials(server_name, username, password)
                
                # Remove from config but keep other data
                config['password'] = '[ENCRYPTED]'  # Marker
                migrated_count += 1
    
    if migrated_count > 0:
        # Save updated servers data
        settings.setValue("servers", servers)
        settings.sync()
        print(f"Migrated {migrated_count} server passwords to secure storage")
    
    return migrated_count