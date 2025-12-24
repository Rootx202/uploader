import paramiko
import os
from models.protocols.base import BaseUploader

class SFTPUploader(BaseUploader):
    def __init__(self, host, port, username, password, **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sftp = None
        self.transport = None
        
    def connect(self):
        try:
            self.transport = paramiko.Transport((self.host, self.port))
            self.transport.connect(username=self.username, password=self.password)
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            self.is_connected = True
            return True, "Connected successfully"
        except Exception as e:
            self.is_connected = False
            return False, f"Connection failed: {str(e)}"
            
    def disconnect(self):
        if self.sftp:
            self.sftp.close()
        if self.transport:
            self.transport.close()
        super().disconnect()
        
    def create_remote_directory(self, remote_path):
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            path_parts = remote_path.split('/')
            current_path = ""
            
            for part in path_parts:
                if not part:
                    continue
                    
                current_path += f"/{part}"
                try:
                    self.sftp.stat(current_path)
                except FileNotFoundError:
                    self.sftp.mkdir(current_path)
                    
            return True, "Directory created successfully"
        except Exception as e:
            return False, f"Failed to create directory: {str(e)}"
            
    def upload_file(self, local_path, remote_path, progress_callback=None):
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                self.create_remote_directory(remote_dir)
                
            file_size = os.path.getsize(local_path)
            
            class ProgressTracker:
                def __init__(self, callback, parent_uploader):
                    self.callback = callback
                    self.uploaded = 0
                    self.parent = parent_uploader
                    
                def progress(self, transferred, total):
                    if self.parent.should_cancel:
                        return
                        
                    self.uploaded = transferred
                    self.parent._throttle_bandwidth(transferred - self.uploaded)
                    
                    if self.callback:
                        self.callback(transferred / total * 100)
            
            tracker = ProgressTracker(progress_callback, self)
            self.sftp.put(local_path, remote_path, callback=tracker.progress)
                
            return True, "File uploaded successfully"
        except Exception as e:
            return False, f"Upload failed: {str(e)}"
    
    def list_directory(self, remote_path="/"):
        """List files and directories in remote path"""
        if not self.is_connected:
            return False, []
            
        try:
            items = []
            
            # List directory contents
            entries = self.sftp.listdir_attr(remote_path)
            
            for entry in entries:
                # Skip . and .. entries
                if entry.filename in ['.', '..']:
                    continue
                
                # Determine if it's a directory
                import stat
                is_directory = stat.S_ISDIR(entry.st_mode) if entry.st_mode else False
                
                # Format full path
                full_path = f"{remote_path.rstrip('/')}/{entry.filename}"
                
                # Get modification time
                modified = entry.st_mtime if hasattr(entry, 'st_mtime') else None
                if modified:
                    from datetime import datetime
                    modified = datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M:%S')
                
                item = {
                    'name': entry.filename,
                    'type': 'directory' if is_directory else 'file',
                    'size': entry.st_size if hasattr(entry, 'st_size') and entry.st_size else 0,
                    'permissions': oct(entry.st_mode)[-3:] if entry.st_mode else '755',
                    'full_path': full_path,
                    'modified': modified
                }
                items.append(item)
            
            return True, items
            
        except Exception as e:
            return False, []
    
    def get_file_info(self, remote_path):
        """Get detailed info about a remote file/directory"""
        if not self.is_connected:
            return False, {}
            
        try:
            stat_result = self.sftp.stat(remote_path)
            
            import stat as stat_module
            is_directory = stat_module.S_ISDIR(stat_result.st_mode)
            
            from datetime import datetime
            modified = datetime.fromtimestamp(stat_result.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            info = {
                'name': os.path.basename(remote_path),
                'type': 'directory' if is_directory else 'file',
                'size': stat_result.st_size if not is_directory else 0,
                'permissions': oct(stat_result.st_mode)[-3:],
                'full_path': remote_path,
                'modified': modified
            }
            
            return True, info
            
        except Exception as e:
            return False, {}
    
    def download_file(self, remote_path, local_path, progress_callback=None):
        """Download a file from remote server"""
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            # Get file size for progress calculation
            try:
                stat_result = self.sftp.stat(remote_path)
                file_size = stat_result.st_size
            except:
                file_size = 0
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            class ProgressTracker:
                def __init__(self, callback, parent_uploader):
                    self.callback = callback
                    self.downloaded = 0
                    self.parent = parent_uploader
                    
                def progress(self, transferred, total):
                    if self.parent.should_cancel:
                        return
                        
                    self.downloaded = transferred
                    
                    if self.callback and total > 0:
                        self.callback(transferred / total * 100)
            
            tracker = ProgressTracker(progress_callback, self)
            self.sftp.get(remote_path, local_path, callback=tracker.progress)
                
            return True, "File downloaded successfully"
            
        except Exception as e:
            return False, f"Download failed: {str(e)}"
    
    def delete_file(self, remote_path):
        """Delete a remote file or directory"""
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            # Check if it's a file or directory
            stat_result = self.sftp.stat(remote_path)
            
            import stat
            if stat.S_ISDIR(stat_result.st_mode):
                # It's a directory
                self.sftp.rmdir(remote_path)
                return True, "Directory deleted successfully"
            else:
                # It's a file
                self.sftp.remove(remote_path)
                return True, "File deleted successfully"
                    
        except Exception as e:
            return False, f"Delete failed: {str(e)}"
    
    def create_directory(self, remote_path):
        """Create a remote directory"""
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            self.sftp.mkdir(remote_path)
            return True, "Directory created successfully"
        except Exception as e:
            return False, f"Failed to create directory: {str(e)}"
