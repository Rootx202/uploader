import time
import hashlib
from typing import Tuple

class BaseUploader:
    """Base class for all uploaders with common functionality"""
    
    def __init__(self, **kwargs):
        self.is_connected = False
        self.should_cancel = False
        self.bandwidth_limit = kwargs.get('bandwidth_limit', 0)  # KB/s, 0 = unlimited
        self.last_byte_time = time.time()
        self.bytes_transferred = 0
        
    def connect(self) -> Tuple[bool, str]:
        """Connect to the remote server"""
        raise NotImplementedError("Subclasses must implement connect method")
        
    def disconnect(self):
        """Disconnect from the remote server"""
        self.is_connected = False
        
    def set_cancel(self, should_cancel: bool):
        """Set the cancel flag"""
        self.should_cancel = should_cancel
        
    def create_remote_directory(self, remote_path: str) -> Tuple[bool, str]:
        """Create remote directory structure"""
        raise NotImplementedError("Subclasses must implement create_remote_directory method")
        
    def upload_file(self, local_path: str, remote_path: str, progress_callback=None) -> Tuple[bool, str]:
        """Upload a single file"""
        raise NotImplementedError("Subclasses must implement upload_file method")
        
    def _throttle_bandwidth(self, bytes_sent: int):
        """Throttle bandwidth if limit is set"""
        if self.bandwidth_limit <= 0:
            return
            
        current_time = time.time()
        elapsed = current_time - self.last_byte_time
        self.bytes_transferred += bytes_sent
        
        # Calculate required delay to maintain bandwidth limit
        expected_time = self.bytes_transferred / (self.bandwidth_limit * 1024)  # Convert KB/s to bytes/s
        actual_time = current_time - self.last_byte_time
        
        if actual_time < expected_time:
            time.sleep(expected_time - actual_time)
            
    def get_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
        
    def list_directory(self, remote_path: str = "/") -> Tuple[bool, list]:
        """List files and directories in remote path"""
        raise NotImplementedError("Subclasses must implement list_directory method")
        
    def get_file_info(self, remote_path: str) -> Tuple[bool, dict]:
        """Get detailed info about a remote file/directory"""
        raise NotImplementedError("Subclasses must implement get_file_info method")
        
    def download_file(self, remote_path: str, local_path: str, progress_callback=None) -> Tuple[bool, str]:
        """Download a file from remote server"""
        raise NotImplementedError("Subclasses must implement download_file method")
        
    def delete_file(self, remote_path: str) -> Tuple[bool, str]:
        """Delete a remote file"""
        raise NotImplementedError("Subclasses must implement delete_file method")
        
    def create_directory(self, remote_path: str) -> Tuple[bool, str]:
        """Create a remote directory"""
        raise NotImplementedError("Subclasses must implement create_directory method")
