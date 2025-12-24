import ftplib
import os
from models.protocols.base import BaseUploader

class FTPUploader(BaseUploader):
    def __init__(self, host, port, username, password, use_tls=False, **kwargs):
        super().__init__(**kwargs)
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.ftp = None
        
    def connect(self):
        try:
            if self.use_tls:
                self.ftp = ftplib.FTP_TLS()
            else:
                self.ftp = ftplib.FTP()
                
            self.ftp.connect(self.host, self.port)
            self.ftp.login(self.username, self.password)
            
            if self.use_tls:
                self.ftp.prot_p()  # Set up secure data connection
                
            self.is_connected = True
            return True, "Connected successfully"
        except Exception as e:
            self.is_connected = False
            return False, f"Connection failed: {str(e)}"
            
    def disconnect(self):
        if self.ftp and self.is_connected:
            try:
                self.ftp.quit()
            except:
                self.ftp.close()
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
                    self.ftp.cwd(current_path)
                except ftplib.error_perm:
                    self.ftp.mkd(current_path)
                    self.ftp.cwd(current_path)
                    
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
                
            self.ftp.cwd('/')
            
            file_size = os.path.getsize(local_path)
            with open(local_path, 'rb') as file:
                uploaded = 0
                
                def callback(data):
                    nonlocal uploaded
                    if self.should_cancel:
                        return
                        
                    uploaded += len(data)
                    self._throttle_bandwidth(len(data))
                    
                    if progress_callback:
                        progress_callback(uploaded / file_size * 100)
                    return data
                    
                self.ftp.storbinary(f'STOR {remote_path}', file, 8192, callback)
                
            return True, "File uploaded successfully"
        except Exception as e:
            return False, f"Upload failed: {str(e)}"
    
    def list_directory(self, remote_path="/"):
        """List files and directories in remote path"""
        if not self.is_connected:
            return False, []
            
        try:
            items = []
            original_dir = self.ftp.pwd()
            
            try:
                self.ftp.cwd(remote_path)
                current_dir = self.ftp.pwd()
                
                # Get directory listing with details
                files_data = []
                self.ftp.retrlines('LIST', files_data.append)
                
                for line in files_data:
                    if not line.strip():
                        continue
                        
                    # Parse FTP LIST format
                    parts = line.split()
                    if len(parts) < 9:
                        continue
                    
                    permissions = parts[0]
                    size = parts[4] if parts[4].isdigit() else 0
                    name = ' '.join(parts[8:])
                    
                    # Skip . and .. entries
                    if name in ['.', '..']:
                        continue
                    
                    is_directory = permissions.startswith('d')
                    
                    item = {
                        'name': name,
                        'type': 'directory' if is_directory else 'file',
                        'size': int(size) if not is_directory else 0,
                        'permissions': permissions,
                        'full_path': f"{current_dir.rstrip('/')}/{name}",
                        'modified': None  # FTP LIST doesn't always provide reliable dates
                    }
                    items.append(item)
                    
            finally:
                # Return to original directory
                try:
                    self.ftp.cwd(original_dir)
                except:
                    pass
                    
            return True, items
            
        except Exception as e:
            return False, []
    
    def get_file_info(self, remote_path):
        """Get detailed info about a remote file/directory"""
        if not self.is_connected:
            return False, {}
            
        try:
            # Try to get file size
            try:
                size = self.ftp.size(remote_path)
                file_type = 'file'
            except:
                size = 0
                file_type = 'directory'
            
            info = {
                'name': os.path.basename(remote_path),
                'type': file_type,
                'size': size,
                'full_path': remote_path
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
                file_size = self.ftp.size(remote_path)
            except:
                file_size = 0
            
            downloaded = 0
            
            def callback(data):
                nonlocal downloaded
                if self.should_cancel:
                    return
                    
                downloaded += len(data)
                
                if progress_callback and file_size > 0:
                    progress_callback(downloaded / file_size * 100)
                
                return data
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with open(local_path, 'wb') as local_file:
                self.ftp.retrbinary(f'RETR {remote_path}', callback)
                
            return True, "File downloaded successfully"
            
        except Exception as e:
            return False, f"Download failed: {str(e)}"
    
    def delete_file(self, remote_path):
        """Delete a remote file"""
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            # Check if it's a file or directory
            try:
                self.ftp.size(remote_path)
                # It's a file
                self.ftp.delete(remote_path)
                return True, "File deleted successfully"
            except:
                # It might be a directory
                try:
                    self.ftp.rmd(remote_path)
                    return True, "Directory deleted successfully"
                except Exception as e:
                    return False, f"Delete failed: {str(e)}"
                    
        except Exception as e:
            return False, f"Delete failed: {str(e)}"
    
    def create_directory(self, remote_path):
        """Create a remote directory"""
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            self.ftp.mkd(remote_path)
            return True, "Directory created successfully"
        except Exception as e:
            return False, f"Failed to create directory: {str(e)}"
