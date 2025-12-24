import os
import requests
from requests.auth import HTTPBasicAuth
from models.protocols.base import BaseUploader

try:
    import requests
    from requests.auth import HTTPBasicAuth
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

class HTTPUploader(BaseUploader):
    def __init__(self, url, method='POST', auth_type='none', username='', password='', headers=None, **kwargs):
        super().__init__(**kwargs)
        self.url = url
        self.method = method.upper()
        self.auth_type = auth_type
        self.username = username
        self.password = password
        self.headers = headers or {}
        self.session = None
    
    def disconnect(self):
        if self.session:
            self.session.close()
        super().disconnect()
        
    def connect(self):
        if not HAS_REQUESTS:
            return False, "requests library not installed"
            
        try:
            self.session = requests.Session()
            
            # Set up authentication
            if self.auth_type == 'basic' and self.username and self.password:
                self.session.auth = HTTPBasicAuth(self.username, self.password)
            elif self.auth_type == 'bearer' and self.password:
                self.headers['Authorization'] = f'Bearer {self.password}'
                
            self.session.headers.update(self.headers)
            
            # Test connection with a HEAD request
            response = self.session.head(self.url)
            if response.status_code < 400:
                self.is_connected = True
                return True, "Connected successfully"
            else:
                return False, f"HTTP {response.status_code}: {response.reason}"
                
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
            
    def create_remote_directory(self, remote_path):
        return True, "HTTP doesn't require directory creation"
        
    def upload_file(self, local_path, remote_path, progress_callback=None):
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            file_size = os.path.getsize(local_path)
            
            with open(local_path, 'rb') as f:
                files = {'file': (os.path.basename(local_path), f, 'application/octet-stream')}
                
                if self.method == 'POST':
                    response = self.session.post(self.url, files=files)
                elif self.method == 'PUT':
                    response = self.session.put(self.url, data=f)
                else:
                    return False, f"Unsupported HTTP method: {self.method}"
                    
                if response.status_code < 300:
                    if progress_callback:
                        progress_callback(100.0)
                    return True, "File uploaded successfully"
                else:
                    return False, f"HTTP {response.status_code}: {response.text[:200]}"
                    
        except Exception as e:
            return False, f"Upload failed: {str(e)}"
